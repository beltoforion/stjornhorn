from __future__ import annotations

from enum import IntEnum

import numpy as np
from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import NodeParam, NodeParamType, SourceNodeBase
from core.port import OutputPort


class GradientDirection(IntEnum):
    """Axis selector for :class:`GradientSource`.

    Backed by :class:`IntEnum` so the integer representation persists
    cleanly across saved flow files: JSON stores the int, the setter
    accepts both ints and enum members, and the ``ENUM`` param widget
    renders a combo box of ``name``-based labels.
    """
    VERTICAL   = 0  # gradient runs along Y
    HORIZONTAL = 1  # gradient runs along X
    RADIAL     = 2  # gradient runs from the centre outward (always symmetric)


class GradientMode(IntEnum):
    """Symmetry selector for :class:`GradientSource`.

    ``SYMMETRIC`` produces a "double" gradient that is mirrored around
    the image centre — 0 in the middle, ramping to 255 at *both* ends
    of the chosen axis. This is the right shape for tilt-shift,
    vignette and any other compositing that needs to fade out toward
    both edges.

    ``LINEAR`` produces a single-sided gradient — 0 at one end of the
    axis, 255 at the other — which is what cross-fades, day/night
    transitions, soft-edge wipes and similar one-way blends need. Has
    no effect when ``direction = RADIAL``: a radial gradient is
    inherently rotation-symmetric, so a "linear radial" has no
    meaningful interpretation; the node falls back to the symmetric
    ramp in that case.
    """
    SYMMETRIC = 0  # 0 in the middle, 255 at both ends (the "double" gradient)
    LINEAR    = 1  # 0 at one end, 255 at the other


class GradientSource(SourceNodeBase):
    """Procedurally generates a single-channel greyscale gradient image.

    Emits a 2-D ``uint8`` image where each pixel encodes a normalised
    distance along the chosen axis, mapped through an optional
    plateau + smooth ramp. Designed as the procedural mask source
    that :class:`~nodes.filters.masked_blend.MaskedBlend` consumes —
    drop one in to soft-mask any per-frame compositing pipeline
    (tilt-shift blur, vignette, cross-fade, soft-edge wipe, …)
    without having to ship a hand-painted PNG.

    Parameters:
      width, height -- output image size in pixels.
      direction     -- VERTICAL / HORIZONTAL / RADIAL axis along which
                       the gradient grows.
      mode          -- SYMMETRIC (mirrored around the centre, the
                       classic "double" gradient — tilt-shift,
                       vignette) or LINEAR (one-sided 0 → 255 — cross
                       fades, wipes). Ignored when ``direction =
                       RADIAL``.
      band_width    -- normalised plateau width where the mask stays
                       at 0. In SYMMETRIC mode this is the half-width
                       of a centre band: ``0.0`` = no plateau,
                       ``0.5`` = inner half flat. In LINEAR mode this
                       is the leading dead-zone before the ramp
                       starts: ``0.0`` = ramp from the very first
                       pixel, ``0.5`` = first half of the image
                       stays at 0 then ramps to 255 over the second
                       half. Clamped to ``[0, 1)``.
      smooth        -- when ``True`` (default) the ramp is cosine-eased
                       for a photographic falloff; when ``False`` the
                       ramp is linear, which is preferable when the
                       mask drives a numeric blend that should stay
                       proportional to distance.

    Reactive: the node editor re-runs the flow whenever any parameter
    on any node changes, so size / direction / mode / band edits
    update the downstream preview live without pressing Run.
    """

    def __init__(self) -> None:
        super().__init__("Gradient Source", section="Sources")
        self._width:      int   = 512
        self._height:     int   = 512
        self._direction:  GradientDirection = GradientDirection.VERTICAL
        self._mode:       GradientMode      = GradientMode.SYMMETRIC
        self._band_width: float = 0.2
        self._smooth:     bool  = True

        self._add_param(NodeParam("width",  NodeParamType.INT,  default=512))
        self._add_param(NodeParam("height", NodeParamType.INT,  default=512))
        self._add_param(NodeParam(
            "direction",
            NodeParamType.ENUM,
            default=GradientDirection.VERTICAL,
            metadata={"enum": GradientDirection},
        ))
        self._add_param(NodeParam(
            "mode",
            NodeParamType.ENUM,
            default=GradientMode.SYMMETRIC,
            metadata={"enum": GradientMode},
        ))
        self._add_param(NodeParam("band_width", NodeParamType.FLOAT, default=0.2))
        self._add_param(NodeParam("smooth",     NodeParamType.BOOL,  default=True))
        self._add_output(OutputPort("image", {IoDataType.IMAGE_GREY}))

        self._apply_default_params()

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def width(self) -> int:
        return self._width

    @width.setter
    def width(self, value: int) -> None:
        v = int(value)
        if v < 1:
            raise ValueError(f"width must be >= 1 (got {v})")
        self._width = v

    @property
    def height(self) -> int:
        return self._height

    @height.setter
    def height(self, value: int) -> None:
        v = int(value)
        if v < 1:
            raise ValueError(f"height must be >= 1 (got {v})")
        self._height = v

    @property
    def direction(self) -> GradientDirection:
        return self._direction

    @direction.setter
    def direction(self, value: int | GradientDirection) -> None:
        try:
            self._direction = GradientDirection(value)
        except ValueError as e:
            raise ValueError(
                f"direction must be one of {[m.value for m in GradientDirection]} "
                f"(got {value!r})"
            ) from e

    @property
    def mode(self) -> GradientMode:
        return self._mode

    @mode.setter
    def mode(self, value: int | GradientMode) -> None:
        try:
            self._mode = GradientMode(value)
        except ValueError as e:
            raise ValueError(
                f"mode must be one of {[m.value for m in GradientMode]} "
                f"(got {value!r})"
            ) from e

    @property
    def band_width(self) -> float:
        return self._band_width

    @band_width.setter
    def band_width(self, value: float) -> None:
        v = float(value)
        # Clamp to [0, 1) — at exactly 1.0 the ramp denominator is zero,
        # which would just produce an all-zero image; clip a hair below
        # so the node still emits a meaningful gradient at the extreme.
        self._band_width = max(0.0, min(0.999, v))

    @property
    def smooth(self) -> bool:
        return self._smooth

    @smooth.setter
    def smooth(self, value: bool) -> None:
        self._smooth = bool(value)

    # ── SourceNodeBase interface ────────────────────────────────────────────────

    @property
    @override
    def is_reactive(self) -> bool:
        # Single deterministic frame: re-run on any param edit so the
        # downstream preview tracks the gradient live.
        return True

    @override
    def process_impl(self) -> None:
        self.outputs[0].send(IoData.from_greyscale(self._build_gradient()))

    # ── Internals ──────────────────────────────────────────────────────────────

    def _build_gradient(self) -> np.ndarray:
        """Return the configured gradient as a ``uint8`` (H, W) array.

        Per-axis distance metric depends on ``mode``:

        * SYMMETRIC — distance from the centre, normalised so the far
          edge along the axis reads 1.0. Produces a double gradient
          (mirrored around the centre).
        * LINEAR — distance from the *start* of the axis, normalised
          so the far end reads 1.0. Produces a single-sided gradient.

        RADIAL ignores ``mode`` and always uses the centred metric;
        a "linear" radial has no meaningful interpretation.
        """
        h, w = self._height, self._width
        symmetric = (self._mode == GradientMode.SYMMETRIC)

        if self._direction == GradientDirection.VERTICAL:
            y = np.arange(h, dtype=np.float32)
            if symmetric:
                cy = max((h - 1) / 2.0, 1e-9)
                d_axis = np.abs(y - cy) / cy
            else:
                d_axis = y / max(h - 1, 1)         # 0 at top, 1 at bottom
            d = np.tile(d_axis[:, None], (1, w))
        elif self._direction == GradientDirection.HORIZONTAL:
            x = np.arange(w, dtype=np.float32)
            if symmetric:
                cx = max((w - 1) / 2.0, 1e-9)
                d_axis = np.abs(x - cx) / cx
            else:
                d_axis = x / max(w - 1, 1)         # 0 at left, 1 at right
            d = np.tile(d_axis[None, :], (h, 1))
        else:  # RADIAL — always symmetric (mode is irrelevant here)
            cx = max((w - 1) / 2.0, 1e-9)
            cy = max((h - 1) / 2.0, 1e-9)
            yy = (np.arange(h, dtype=np.float32) - cy) / cy
            xx = (np.arange(w, dtype=np.float32) - cx) / cx
            d = np.sqrt(yy[:, None] ** 2 + xx[None, :] ** 2)
            # Distance to a corner exceeds 1 in a non-square image —
            # clip so the ramp denominator stays well-defined and the
            # corners read as the maximum 255.
            np.clip(d, 0.0, 1.0, out=d)

        # Carve out the leading plateau and remap the remainder to
        # [0, 1] so the ramp covers the full output range.
        bw = self._band_width
        ramp = np.clip((d - bw) / max(1.0 - bw, 1e-9), 0.0, 1.0)
        if self._smooth:
            ramp = (1.0 - np.cos(ramp * np.pi)) * 0.5

        return (ramp * 255.0).astype(np.uint8)

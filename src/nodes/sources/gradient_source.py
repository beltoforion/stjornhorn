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
    VERTICAL   = 0  # gradient runs along Y, plateau is a horizontal band
    HORIZONTAL = 1  # gradient runs along X, plateau is a vertical band
    RADIAL     = 2  # gradient runs from the centre outward


class GradientSource(SourceNodeBase):
    """Procedurally generates a single-channel greyscale gradient image.

    Emits a 2-D ``uint8`` image where each pixel encodes a normalised
    distance from the centre of the chosen axis: 0 in the central
    plateau, 255 at the far edge, with a configurable smooth ramp
    in between. Designed as the procedural mask source that
    :class:`~nodes.filters.masked_blend.MaskedBlend` consumes — drop
    one in to soft-mask any per-frame compositing pipeline (tilt-shift
    blur, vignette, tone-mapped centre highlights, …) without having
    to ship a hand-painted PNG.

    Parameters:
      width, height -- output image size in pixels.
      direction     -- VERTICAL / HORIZONTAL / RADIAL axis along which
                       the gradient grows.
      band_width    -- normalised half-width of the central plateau where
                       the mask stays at 0. ``0.0`` = no plateau (immediate
                       ramp from the centre outward), ``0.5`` = plateau
                       fills the inner half of the image. Clamped to
                       ``[0, 1)``.
      smooth        -- when ``True`` (default) the ramp is cosine-eased so
                       the transition feels photographic; when ``False``
                       the ramp is linear, which is preferable when the
                       mask drives a numeric blend that should stay
                       proportional to distance.

    Reactive: the node editor re-runs the flow whenever any parameter
    on any node changes, so size / direction / band edits update the
    downstream preview live without pressing Run.
    """

    def __init__(self) -> None:
        super().__init__("Gradient Source", section="Sources")
        self._width:      int   = 512
        self._height:     int   = 512
        self._direction:  GradientDirection = GradientDirection.VERTICAL
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
        """Return the configured gradient as a ``uint8`` (H, W) array."""
        h, w = self._height, self._width

        # Normalised distance from the image centre, in [0, 1] at the
        # far edge along the relevant axis. The vertical / horizontal
        # variants degenerate to a 1-D ramp tiled across the other
        # axis; the radial variant is a true 2-D field.
        if self._direction == GradientDirection.VERTICAL:
            cy = max((h - 1) / 2.0, 1e-9)
            y = np.arange(h, dtype=np.float32)
            d = np.abs(y - cy) / cy            # shape (H,)
            d = np.tile(d[:, None], (1, w))    # broadcast to (H, W)
        elif self._direction == GradientDirection.HORIZONTAL:
            cx = max((w - 1) / 2.0, 1e-9)
            x = np.arange(w, dtype=np.float32)
            d = np.abs(x - cx) / cx
            d = np.tile(d[None, :], (h, 1))
        else:  # RADIAL
            cx = max((w - 1) / 2.0, 1e-9)
            cy = max((h - 1) / 2.0, 1e-9)
            yy = (np.arange(h, dtype=np.float32) - cy) / cy
            xx = (np.arange(w, dtype=np.float32) - cx) / cx
            d = np.sqrt(yy[:, None] ** 2 + xx[None, :] ** 2)
            # Distance to a corner exceeds 1 in a non-square image —
            # clip so the ramp denominator stays well-defined and the
            # corners read as the maximum 255.
            np.clip(d, 0.0, 1.0, out=d)

        # Carve out the central plateau and remap the remainder to
        # [0, 1] so the ramp covers the full output range.
        bw = self._band_width
        ramp = np.clip((d - bw) / max(1.0 - bw, 1e-9), 0.0, 1.0)
        if self._smooth:
            ramp = (1.0 - np.cos(ramp * np.pi)) * 0.5

        return (ramp * 255.0).astype(np.uint8)

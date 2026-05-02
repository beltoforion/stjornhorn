from __future__ import annotations

from enum import IntEnum

import numpy as np
from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import SourceNodeBase
from core.params import BoolParam, ClampedFloatParam, EnumParam, IntParam
from core.port import OutputPort


class GradientDirection(IntEnum):
    """Axis selector for :class:`GradientSource`."""
    VERTICAL   = 0  # gradient runs along Y
    HORIZONTAL = 1  # gradient runs along X
    RADIAL     = 2  # gradient runs from the centre outward (always symmetric)


class GradientMode(IntEnum):
    """Symmetry selector for :class:`GradientSource`.

    ``SYMMETRIC`` produces a centre-mirrored gradient (0 in the
    middle, 255 at both ends) — tilt-shift, vignette. ``LINEAR``
    produces a one-sided gradient (0 → 255) — cross-fades, wipes.
    Ignored when ``direction = RADIAL`` (always symmetric).
    """
    SYMMETRIC = 0  # 0 in the middle, 255 at both ends (the "double" gradient)
    LINEAR    = 1  # 0 at one end, 255 at the other


class GradientSource(SourceNodeBase):
    """Procedurally generates a single-channel greyscale gradient image.

    Emits a uint8 image where each pixel encodes a normalised distance
    along the chosen axis, mapped through an optional plateau and
    smooth ramp. Useful as a procedural mask for :class:`MaskedBlend`
    (tilt-shift, vignette, cross-fade) without having to ship a
    hand-painted PNG. Reactive: re-runs on any parameter edit.
    """

    width = IntParam(512, min=1, constant=True)
    height = IntParam(512, min=1, constant=True)
    direction = EnumParam(GradientDirection, GradientDirection.VERTICAL, constant=True)
    mode = EnumParam(GradientMode, GradientMode.SYMMETRIC, constant=True)
    # band_width clamps to [0, 0.999]: at 1.0 the ramp denominator is
    # zero (all-zero image), so clip a hair below — and clamp instead
    # of raising so a slider sweep past the extreme just saturates.
    band_width = ClampedFloatParam(0.2, min=0.0, max=0.999, constant=True)
    smooth = BoolParam(True, constant=True)

    HEADER_ICON = "gradient"

    def __init__(self) -> None:
        super().__init__("Gradient Source", section="Sources")
        self._add_output(OutputPort("image", {IoDataType.IMAGE_GREY}))
        self._apply_default_params()

    @property
    @override
    def is_reactive(self) -> bool:
        # Single deterministic frame: re-run on any param edit so the
        # downstream preview tracks the gradient live.
        return True

    @override
    def tick_count(self) -> int | None:
        return 1

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

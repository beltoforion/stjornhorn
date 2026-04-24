from __future__ import annotations

import cv2
import numpy as np
from typing_extensions import override

from core.io_data import IMAGE_TYPES, IoData, IoDataType
from core.node_base import NodeBase, NodeParam, NodeParamType
from core.port import InputPort, OutputPort


class Overlay(NodeBase):
    """Composite an overlay image onto a base image.

    The overlay input is optionally resized by ``scale``, rotated by
    ``angle`` degrees (counter-clockwise, around the overlay's centre,
    with the bounding box expanded so no pixels are lost) and then
    blended onto the base at ``(xpos, ypos)`` with opacity ``alpha``.
    The output canvas always matches the base image — any part of the
    transformed overlay that falls outside the base is clipped.

    Type strategy:
      If either input is colour (:data:`IoDataType.IMAGE`), any
      greyscale input is promoted to BGR via
      ``cv2.cvtColor(..., COLOR_GRAY2BGR)`` and the output is emitted
      as ``IMAGE``. If both inputs are greyscale, the output stays
      greyscale.
    """

    def __init__(self) -> None:
        super().__init__("Overlay", section="Composit")

        self._scale: float = 1.0
        self._angle: float = 0.0
        self._xpos:  int   = 0
        self._ypos:  int   = 0
        self._alpha: float = 1.0

        self._add_input(InputPort("image", set(IMAGE_TYPES)))
        self._add_input(InputPort("overlay", set(IMAGE_TYPES)))
        self._add_output(OutputPort("image", set(IMAGE_TYPES)))

        self._apply_default_params()

    # ── Parameters ─────────────────────────────────────────────────────────────

    @property
    @override
    def params(self) -> list[NodeParam]:
        return [
            NodeParam("scale", NodeParamType.FLOAT, {"default": 1.0}),
            NodeParam("angle", NodeParamType.FLOAT, {"default": 0.0}),
            NodeParam("xpos",  NodeParamType.INT,   {"default": 0}),
            NodeParam("ypos",  NodeParamType.INT,   {"default": 0}),
            NodeParam("alpha", NodeParamType.FLOAT, {"default": 1.0}),
        ]

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def scale(self) -> float:
        return self._scale

    @scale.setter
    def scale(self, value: float) -> None:
        v = float(value)
        if v <= 0.0:
            raise ValueError(f"scale must be > 0 (got {v})")
        self._scale = v

    @property
    def angle(self) -> float:
        return self._angle

    @angle.setter
    def angle(self, value: float) -> None:
        self._angle = float(value)

    @property
    def xpos(self) -> int:
        return self._xpos

    @xpos.setter
    def xpos(self, value: int) -> None:
        self._xpos = int(value)

    @property
    def ypos(self) -> int:
        return self._ypos

    @ypos.setter
    def ypos(self, value: int) -> None:
        self._ypos = int(value)

    @property
    def alpha(self) -> float:
        return self._alpha

    @alpha.setter
    def alpha(self, value: float) -> None:
        v = float(value)
        # Clamp to [0, 1] so cv2.addWeighted stays well-defined.
        self._alpha = max(0.0, min(1.0, v))

    # ── NodeBase interface ─────────────────────────────────────────────────────

    @override
    def process_impl(self) -> None:
        base_data    = self.inputs[0].data
        overlay_data = self.inputs[1].data

        any_color = (
            base_data.type == IoDataType.IMAGE
            or overlay_data.type == IoDataType.IMAGE
        )

        def to_canvas(d: IoData) -> np.ndarray:
            if any_color and d.type == IoDataType.IMAGE_GREY:
                return cv2.cvtColor(d.image, cv2.COLOR_GRAY2BGR)
            return d.image

        # ── Skip path 1: alpha == 0 ───────────────────────────────────────
        # Overlay is invisible — no warp, no copy, no blend. Forward the
        # (possibly grey→BGR promoted) base straight through.
        if self._alpha == 0.0:
            self._emit(to_canvas(base_data), any_color)
            return

        overlay_src = to_canvas(overlay_data)
        src_h, src_w = overlay_src.shape[:2]

        # ── Predict the transformed overlay's bounding box (no warp yet) ──
        # cheap enough to always compute, so we can decide whether to
        # bother with the expensive warpAffine / resize / base.copy().
        rotates = self._angle % 360.0 != 0.0
        if rotates:
            center = (src_w / 2.0, src_h / 2.0)
            M = cv2.getRotationMatrix2D(center, self._angle, self._scale)
            cos = abs(M[0, 0])
            sin = abs(M[0, 1])
            out_w = max(1, int(round(src_h * sin + src_w * cos)))
            out_h = max(1, int(round(src_h * cos + src_w * sin)))
        elif self._scale != 1.0:
            out_w = max(1, int(round(src_w * self._scale)))
            out_h = max(1, int(round(src_h * self._scale)))
        else:
            out_w, out_h = src_w, src_h

        base_src = to_canvas(base_data)
        base_h, base_w = base_src.shape[:2]

        # Destination rectangle on the base, clipped to the base bounds.
        x0 = max(self._xpos, 0)
        y0 = max(self._ypos, 0)
        x1 = min(self._xpos + out_w, base_w)
        y1 = min(self._ypos + out_h, base_h)

        # ── Skip path 2: transformed overlay misses the base entirely ─────
        # Same deal — pass the base through without warping or copying.
        if x0 >= x1 or y0 >= y1:
            self._emit(base_src, any_color)
            return

        # ── Execute the transform + composite ─────────────────────────────
        if rotates:
            M[0, 2] += (out_w / 2.0) - center[0]
            M[1, 2] += (out_h / 2.0) - center[1]
            overlay = cv2.warpAffine(
                overlay_src, M, (out_w, out_h), flags=cv2.INTER_LINEAR
            )
        elif self._scale != 1.0:
            overlay = cv2.resize(
                overlay_src, (out_w, out_h), interpolation=cv2.INTER_LINEAR
            )
        else:
            overlay = overlay_src

        base = base_src.copy()

        # Matching rectangle inside the overlay (accounts for negative
        # xpos/ypos shifting the overlay off the top-left edge).
        ox0 = x0 - self._xpos
        oy0 = y0 - self._ypos
        ox1 = ox0 + (x1 - x0)
        oy1 = oy0 + (y1 - y0)

        roi     = base[y0:y1, x0:x1]
        ov_crop = overlay[oy0:oy1, ox0:ox1]

        blended = cv2.addWeighted(ov_crop, self._alpha, roi, 1.0 - self._alpha, 0.0)
        base[y0:y1, x0:x1] = blended

        self._emit(base, any_color)

    def _emit(self, image: np.ndarray, any_color: bool) -> None:
        if any_color:
            self.outputs[0].send(IoData.from_image(image))
        else:
            self.outputs[0].send(IoData.from_greyscale(image))

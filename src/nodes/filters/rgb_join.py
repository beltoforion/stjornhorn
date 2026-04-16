from __future__ import annotations

import cv2
import numpy as np
from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase, NodeParam, NodeParamType
from core.port import InputPort, OutputPort


class RgbJoin(NodeBase):
    """Merge three single-channel images into a BGR image.

    Inputs ``B``, ``G`` and ``R`` are combined with ``cv2.merge``. When
    ``three_color`` is enabled, the merged image is further rendered into
    a stylised BGR pattern on a 1.5×/2× upscaled canvas — ported unchanged
    from the original OCVL ``RbgJoinProcessor``.
    """

    def __init__(self) -> None:
        super().__init__("RGB Join", section="Color Spaces")
        self._three_color: bool = False

        self._add_input(InputPort("B", {IoDataType.IMAGE}))
        self._add_input(InputPort("G", {IoDataType.IMAGE}))
        self._add_input(InputPort("R", {IoDataType.IMAGE}))
        self._add_output(OutputPort("image", {IoDataType.IMAGE}))

        # Sync attributes with declared NodeParam defaults; see
        # NodeBase._apply_default_params for rationale.
        self._apply_default_params()

    # ── Parameters ─────────────────────────────────────────────────────────────

    @property
    @override
    def params(self) -> list[NodeParam]:
        return [NodeParam("three_color", NodeParamType.BOOL, {"default": False})]

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def three_color(self) -> bool:
        return self._three_color

    @three_color.setter
    def three_color(self, value: bool) -> None:
        self._three_color = bool(value)

    # ── NodeBase interface ─────────────────────────────────────────────────────

    @override
    def process(self) -> None:
        b = self.inputs[0].data.image
        g = self.inputs[1].data.image
        r = self.inputs[2].data.image

        merged = cv2.merge((b, g, r))
        if self._three_color:
            merged = _rgbify(merged)
        self.outputs[0].send(IoData.from_image(merged))


def _rgbify(image: np.ndarray) -> np.ndarray:
    """Scatter each source pixel's BGR samples across an upscaled canvas.

    Faithful port of OCVL's ``RbgJoinProcessor.__rgbify``. No numba here —
    the loop is O(w*h), so expect it to be slow on large frames; enable
    ``three_color`` only when you want the stylised visualisation.
    """
    h, w, _ = image.shape
    nh = h * 2
    nw = int(w * 1.5)
    rgb = np.zeros((nh, nw, 3), dtype=np.uint8)

    for x in range(w):
        for y in range(h):
            b, g, r = image[y, x, :]
            if x % 2 == 0:
                ox = int(x * 1.5)
                rgb[2 * y + 0, ox,     :] = (0, g, 0)
                rgb[2 * y + 0, ox + 1, :] = (b, 0, 0)
                rgb[2 * y + 1, ox,     :] = (0, 0, r)
            else:
                ox = 1 + int(x * 1.5 - 0.5)
                rgb[2 * y + 0, ox,     :] = (0, 0, r)
                rgb[2 * y + 1, ox,     :] = (b, 0, 0)
                rgb[2 * y + 1, ox - 1, :] = (0, g, 0)
    return rgb

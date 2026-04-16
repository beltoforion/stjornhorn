from __future__ import annotations

import cv2
import numpy as np
from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase, NodeParam, NodeParamType
from core.port import InputPort, OutputPort


class Median(NodeBase):
    """Apply a median blur with a square kernel.

    Wraps ``cv2.medianBlur``; the kernel ``size`` must be odd and ≥ 1.
    Ported from the original OCVL ``MedianProcessor``.
    """

    def __init__(self) -> None:
        super().__init__("Median", section="Processing")
        self._size: int = 3

        self._add_input(InputPort("image", {IoDataType.IMAGE}))
        self._add_output(OutputPort("image", {IoDataType.IMAGE}))

        self._apply_default_params()

    # ── Parameters ─────────────────────────────────────────────────────────────

    @property
    @override
    def params(self) -> list[NodeParam]:
        return [NodeParam("size", NodeParamType.INT, {"default": 3})]

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def size(self) -> int:
        return self._size

    @size.setter
    def size(self, value: int) -> None:
        v = int(value)
        if v < 1:
            raise ValueError(f"size must be >= 1 (got {v})")
        if v % 2 == 0:
            # cv2.medianBlur requires an odd kernel — round up rather than
            # reject so the UI spinbox feels natural when the user types
            # an even number mid-edit.
            v += 1
        self._size = v

    # ── NodeBase interface ─────────────────────────────────────────────────────

    @override
    def process(self) -> None:
        image: np.ndarray = self.inputs[0].data.image
        blurred = cv2.medianBlur(image, self._size)
        self.outputs[0].send(IoData.from_image(blurred))

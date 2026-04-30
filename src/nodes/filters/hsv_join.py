from __future__ import annotations

import cv2
from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase
from core.port import InputPort, OutputPort


class HsvJoin(NodeBase):
    """Merge three single-channel images (H, S, V) into a BGR image.

    Inverse of :class:`HsvSplit`; ``HsvSplit → HsvJoin`` is a
    pixel-exact identity on a BGR input.
    """

    def __init__(self) -> None:
        super().__init__("HSV Join", section="Color Spaces")
        self._add_input(InputPort("H", {IoDataType.IMAGE_GREY}))
        self._add_input(InputPort("S", {IoDataType.IMAGE_GREY}))
        self._add_input(InputPort("V", {IoDataType.IMAGE_GREY}))
        self._add_output(OutputPort("image", {IoDataType.IMAGE}))

    @override
    def process_impl(self) -> None:
        h = self.inputs[0].data.image
        s = self.inputs[1].data.image
        v = self.inputs[2].data.image
        hsv = cv2.merge((h, s, v))
        bgr = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR_FULL)
        self.outputs[0].send(IoData.from_image(bgr))

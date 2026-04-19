from __future__ import annotations

import cv2
import numpy as np
from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase, NodeParam
from core.port import InputPort, OutputPort


class RgbSplit(NodeBase):
    """Split a BGR image into its three channels.

    Emits three single-channel (H×W) :data:`IoDataType.IMAGE_GREY` payloads
    on the ``B``, ``G`` and ``R`` output ports — matching ``cv2.split``'s
    channel order. Ported from the original OCVL ``RgbSplitProcessor``.
    """

    def __init__(self) -> None:
        super().__init__("RGB Split", section="Color Spaces")
        self._add_input(InputPort("image", {IoDataType.IMAGE}))
        self._add_output(OutputPort("B", {IoDataType.IMAGE_GREY}))
        self._add_output(OutputPort("G", {IoDataType.IMAGE_GREY}))
        self._add_output(OutputPort("R", {IoDataType.IMAGE_GREY}))

    @property
    @override
    def params(self) -> list[NodeParam]:
        return []

    @override
    def process_impl(self) -> None:
        image: np.ndarray = self.inputs[0].data.image
        b, g, r = cv2.split(image)
        self.outputs[0].send(IoData.from_greyscale(b))
        self.outputs[1].send(IoData.from_greyscale(g))
        self.outputs[2].send(IoData.from_greyscale(r))

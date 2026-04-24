from __future__ import annotations

import cv2
import numpy as np
from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase, NodeParam
from core.port import InputPort, OutputPort


class Grayscale(NodeBase):
    """Converts a colour image to greyscale.

    Emits a single-channel (H×W) :data:`IoDataType.IMAGE_GREY` payload.
    Downstream nodes that accept ``IMAGE_GREY`` (including the viewer and
    file sink) can consume the output directly; use an :class:`RgbaJoin`
    upstream of colour-only consumers.
    """

    def __init__(self) -> None:
        super().__init__("Grayscale", section="Color Spaces")
        self._add_input(InputPort("image", {IoDataType.IMAGE}))
        self._add_output(OutputPort("image", {IoDataType.IMAGE_GREY}))

    @property
    @override
    def params(self) -> list[NodeParam]:
        return []

    @override
    def process_impl(self) -> None:
        image: np.ndarray = self.inputs[0].data.image
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        self.outputs[0].send(IoData.from_greyscale(gray))

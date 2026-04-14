from __future__ import annotations

import cv2
import numpy as np
from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase, NodeParam
from core.port import InputPort, OutputPort


class Grayscale(NodeBase):
    """Converts a colour image to grayscale.

    The output is a 3-channel BGR image (all three channels identical) so that
    downstream nodes receive a consistent format regardless of whether the
    input was colour or already grayscale.
    """

    def __init__(self) -> None:
        super().__init__("Grayscale")
        self._add_input(InputPort("image",  {IoDataType.IMAGE}))
        self._add_output(OutputPort("image", {IoDataType.IMAGE}))

    @property
    @override
    def params(self) -> list[NodeParam]:
        return []

    @override
    def process(self) -> None:
        image: np.ndarray = self.inputs[0].data.image
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        # Convert back to 3-channel BGR so downstream nodes get a consistent format
        gray_bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        self.outputs[0].send(IoData.from_image(gray_bgr))

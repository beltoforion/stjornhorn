from __future__ import annotations

import cv2
import numpy as np
from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase
from core.port import InputPort, OutputPort


class Grayscale(NodeBase):
    """Converts a colour image to greyscale.

    Emits a single-channel :data:`IoDataType.IMAGE_GREY` payload. Use
    :class:`RgbaJoin` upstream of colour-only consumers.
    """

    HEADER_ICON = "filter_b_and_w"

    def __init__(self) -> None:
        super().__init__("Grayscale", section="Color Spaces")
        self._add_input(InputPort("image", {IoDataType.IMAGE}))
        self._add_output(OutputPort("image", {IoDataType.IMAGE_GREY}))

    @override
    def process_impl(self) -> None:
        in_data = self.inputs[0].data
        image: np.ndarray = in_data.image
        if image.ndim == 3 and image.shape[2] == 4:
            gray = cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)
        else:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        self.outputs[0].send(IoData.from_greyscale(gray, meta=in_data.meta))

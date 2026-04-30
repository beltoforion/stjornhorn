from __future__ import annotations

import cv2
import numpy as np
from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase
from core.port import InputPort, OutputPort


class HsvSplit(NodeBase):
    """Split a BGR image into its HSV components.

    Emits three single-channel greyscale payloads on the ``H``, ``S``
    and ``V`` output ports, with the hue channel using the full
    0..255 range so :class:`HsvJoin` round-trips back to the original
    BGR image. A 4-channel BGRA input is accepted; the alpha channel
    is dropped (HSV has no alpha).
    """

    def __init__(self) -> None:
        super().__init__("HSV Split", section="Color Spaces")
        self._add_input(InputPort("image", {IoDataType.IMAGE}))
        self._add_output(OutputPort("H", {IoDataType.IMAGE_GREY}))
        self._add_output(OutputPort("S", {IoDataType.IMAGE_GREY}))
        self._add_output(OutputPort("V", {IoDataType.IMAGE_GREY}))

    @override
    def process_impl(self) -> None:
        image: np.ndarray = self.inputs[0].data.image
        channels = image.shape[2] if image.ndim == 3 else 1

        if channels == 4:
            image = cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
        elif channels != 3:
            raise ValueError(
                f"HsvSplit expects a 3- or 4-channel image, got {channels}"
            )

        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV_FULL)
        h, s, v = cv2.split(hsv)
        self.outputs[0].send(IoData.from_greyscale(h))
        self.outputs[1].send(IoData.from_greyscale(s))
        self.outputs[2].send(IoData.from_greyscale(v))

from __future__ import annotations

import cv2
import numpy as np
from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase
from core.port import InputPort, OutputPort


class HslSplit(NodeBase):
    """Split a BGR image into its HSL components.

    Emits three single-channel greyscale payloads on the ``H``, ``S``
    and ``L`` output ports, with the hue channel using the full
    0..255 range so :class:`HslJoin` round-trips back to the original
    BGR image. A 4-channel BGRA input is accepted; the alpha channel
    is dropped (HSL has no alpha).
    """

    def __init__(self) -> None:
        super().__init__("HSL Split", section="Color Spaces")
        self._add_input(InputPort("image", {IoDataType.IMAGE}))
        self._add_output(OutputPort("H", {IoDataType.IMAGE_GREY}))
        self._add_output(OutputPort("S", {IoDataType.IMAGE_GREY}))
        self._add_output(OutputPort("L", {IoDataType.IMAGE_GREY}))

    @override
    def process_impl(self) -> None:
        image: np.ndarray = self.inputs[0].data.image
        channels = image.shape[2] if image.ndim == 3 else 1

        if channels == 4:
            image = cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
        elif channels != 3:
            raise ValueError(
                f"HslSplit expects a 3- or 4-channel image, got {channels}"
            )

        hls = cv2.cvtColor(image, cv2.COLOR_BGR2HLS_FULL)
        h, l, s = cv2.split(hls)
        self.outputs[0].send(IoData.from_greyscale(h))
        self.outputs[1].send(IoData.from_greyscale(s))
        self.outputs[2].send(IoData.from_greyscale(l))

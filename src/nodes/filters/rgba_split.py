from __future__ import annotations

import cv2
import numpy as np
from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase
from core.port import InputPort, OutputPort


class RgbaSplit(NodeBase):
    """Split a BGR or BGRA image into its four channels.

    Emits four single-channel greyscale payloads on ``B``, ``G``,
    ``R`` and ``A``. For plain BGR inputs the ``A`` plane is emitted
    as a constant 255 so downstream nodes always see a well-defined
    alpha.
    """

    HEADER_ICON = "call_split"

    def __init__(self) -> None:
        super().__init__("RGBA Split", section="Color Spaces")
        self._add_input(InputPort("image", {IoDataType.IMAGE}))
        self._add_output(OutputPort("B", {IoDataType.IMAGE_GREY}))
        self._add_output(OutputPort("G", {IoDataType.IMAGE_GREY}))
        self._add_output(OutputPort("R", {IoDataType.IMAGE_GREY}))
        self._add_output(OutputPort("A", {IoDataType.IMAGE_GREY}))

    @override
    def process_impl(self) -> None:
        in_data = self.inputs[0].data
        image: np.ndarray = in_data.image
        channels = image.shape[2] if image.ndim == 3 else 1

        if channels == 4:
            b, g, r, a = cv2.split(image)
        elif channels == 3:
            b, g, r = cv2.split(image)
            # Full-opaque plane; same shape / dtype as the colour planes so
            # it composes cleanly with any downstream greyscale filter.
            a = np.full(b.shape, 255, dtype=b.dtype)
        else:
            raise ValueError(
                f"RgbaSplit expects a 3- or 4-channel image, got {channels}"
            )

        # Forward the upstream meta on every output so source_path and
        # custom annotations survive the channel split.
        self.outputs[0].send(IoData.from_greyscale(b, meta=in_data.meta))
        self.outputs[1].send(IoData.from_greyscale(g, meta=in_data.meta))
        self.outputs[2].send(IoData.from_greyscale(r, meta=in_data.meta))
        self.outputs[3].send(IoData.from_greyscale(a, meta=in_data.meta))

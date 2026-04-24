from __future__ import annotations

import cv2
import numpy as np
from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase, NodeParam
from core.port import InputPort, OutputPort


class RgbaSplit(NodeBase):
    """Split a BGR or BGRA image into its four channels.

    Emits four single-channel (H×W) :data:`IoDataType.IMAGE_GREY` payloads
    on the ``B``, ``G``, ``R`` and ``A`` output ports. When the input has
    no alpha (plain BGR, as delivered by :class:`VideoSource` or a JPEG
    read through :class:`ImageSource`), ``A`` is emitted as a constant
    255 plane so downstream nodes always see a well-defined alpha.
    """

    def __init__(self) -> None:
        super().__init__("RGBA Split", section="Color Spaces")
        self._add_input(InputPort("image", {IoDataType.IMAGE}))
        self._add_output(OutputPort("B", {IoDataType.IMAGE_GREY}))
        self._add_output(OutputPort("G", {IoDataType.IMAGE_GREY}))
        self._add_output(OutputPort("R", {IoDataType.IMAGE_GREY}))
        self._add_output(OutputPort("A", {IoDataType.IMAGE_GREY}))

    @property
    @override
    def params(self) -> list[NodeParam]:
        return []

    @override
    def process_impl(self) -> None:
        image: np.ndarray = self.inputs[0].data.image
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

        self.outputs[0].send(IoData.from_greyscale(b))
        self.outputs[1].send(IoData.from_greyscale(g))
        self.outputs[2].send(IoData.from_greyscale(r))
        self.outputs[3].send(IoData.from_greyscale(a))

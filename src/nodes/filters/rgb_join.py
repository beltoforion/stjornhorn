from __future__ import annotations

import cv2
from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase, NodeParam
from core.port import InputPort, OutputPort


class RgbJoin(NodeBase):
    """Merge three single-channel images into a BGR image.

    Inputs ``B``, ``G`` and ``R`` are combined with ``cv2.merge`` and
    emitted as a standard BGR :data:`IoDataType.IMAGE` payload.
    """

    def __init__(self) -> None:
        super().__init__("RGB Join", section="Color Spaces")

        self._add_input(InputPort("B", {IoDataType.IMAGE_GREY}))
        self._add_input(InputPort("G", {IoDataType.IMAGE_GREY}))
        self._add_input(InputPort("R", {IoDataType.IMAGE_GREY}))
        self._add_output(OutputPort("image", {IoDataType.IMAGE}))

    # ── Parameters ─────────────────────────────────────────────────────────────

    @property
    @override
    def params(self) -> list[NodeParam]:
        return []

    # ── NodeBase interface ─────────────────────────────────────────────────────

    @override
    def process_impl(self) -> None:
        b = self.inputs[0].data.image
        g = self.inputs[1].data.image
        r = self.inputs[2].data.image
        self.outputs[0].send(IoData.from_image(cv2.merge((b, g, r))))

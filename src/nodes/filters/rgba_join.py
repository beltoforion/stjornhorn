from __future__ import annotations

import cv2
from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase
from core.port import InputPort, OutputPort


class RgbaJoin(NodeBase):
    """Merge three or four single-channel images into a BGR / BGRA image.

    Inputs ``B``, ``G`` and ``R`` are required. The ``A`` input is
    optional: when it is connected and carries data, the four planes are
    merged into a BGRA :data:`IoDataType.IMAGE` payload; when it is not
    connected, only B/G/R are merged and a plain BGR payload is emitted.
    This keeps pre-existing RGB-only flows working unchanged after
    upgrading to the RGBA-aware split/join pair.
    """

    def __init__(self) -> None:
        super().__init__("RGBA Join", section="Color Spaces")

        self._add_input(InputPort("B", {IoDataType.IMAGE_GREY}))
        self._add_input(InputPort("G", {IoDataType.IMAGE_GREY}))
        self._add_input(InputPort("R", {IoDataType.IMAGE_GREY}))
        self._add_input(InputPort("A", {IoDataType.IMAGE_GREY}, optional=True))
        self._add_output(OutputPort("image", {IoDataType.IMAGE}))

    # ── NodeBase interface ─────────────────────────────────────────────────────

    @override
    def process_impl(self) -> None:
        b = self.inputs[0].data.image
        g = self.inputs[1].data.image
        r = self.inputs[2].data.image
        alpha_port = self.inputs[3]
        if alpha_port.has_data:
            a = alpha_port.data.image
            merged = cv2.merge((b, g, r, a))
        else:
            merged = cv2.merge((b, g, r))
        self.outputs[0].send(IoData.from_image(merged))

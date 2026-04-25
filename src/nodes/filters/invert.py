from __future__ import annotations

import cv2
from typing_extensions import override

from core.io_data import IMAGE_TYPES
from core.node_base import NodeBase, NodeParam
from core.port import InputPort, OutputPort


class Invert(NodeBase):
    """Per-channel image inversion (``255 - pixel``).

    No parameters. Accepts colour or greyscale and emits the same type.
    Wraps :func:`cv2.bitwise_not` so it stays cheap on large frames.
    """

    def __init__(self) -> None:
        super().__init__("Invert", section="Processing")

        self._add_input(InputPort("image", set(IMAGE_TYPES)))
        self._add_output(OutputPort("image", set(IMAGE_TYPES)))

    @property
    @override
    def params(self) -> list[NodeParam]:
        return []

    @override
    def process_impl(self) -> None:
        in_data = self.inputs[0].data
        inverted = cv2.bitwise_not(in_data.image)
        self.outputs[0].send(in_data.with_image(inverted))

from __future__ import annotations

from enum import IntEnum

import cv2
from typing_extensions import override

from core.io_data import IMAGE_TYPES
from core.node_base import NodeBase
from core.params import EnumParam
from core.port import InputPort, OutputPort


class FlipMode(IntEnum):
    """Direction passed to :func:`cv2.flip`.

    Values mirror OpenCV's ``flipCode`` convention exactly so the enum
    member can be passed to :func:`cv2.flip` without a lookup table:
    ``HORIZONTAL = 1`` (mirror around the vertical axis, left↔right),
    ``VERTICAL = 0`` (mirror around the horizontal axis, top↔bottom),
    ``BOTH = -1`` (equivalent to a 180° rotation).
    """
    HORIZONTAL = 1
    VERTICAL   = 0
    BOTH       = -1


class Flip(NodeBase):
    """Mirror an image horizontally, vertically, or both."""

    mode = EnumParam(
        FlipMode,
        FlipMode.HORIZONTAL,
        description=(
            "Flip direction. HORIZONTAL mirrors left/right, "
            "VERTICAL mirrors top/bottom, BOTH does a 180° rotation."
        ),
    )

    def __init__(self) -> None:
        super().__init__("Flip", section="Transform")
        self._add_input(InputPort("image", set(IMAGE_TYPES)))
        self._add_output(OutputPort("image", set(IMAGE_TYPES)))
        self._apply_default_params()

    @override
    def process_impl(self) -> None:
        in_data = self.inputs[0].data
        flipped = cv2.flip(in_data.image, int(self._mode))
        self.outputs[0].send(in_data.with_image(flipped))

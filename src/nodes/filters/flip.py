from __future__ import annotations

from enum import IntEnum

import cv2
from typing_extensions import override

from core.io_data import IMAGE_TYPES
from core.node_base import NodeBase, NodeParam, NodeParamType
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

    def __init__(self) -> None:
        super().__init__("Flip", section="Transform")
        self._mode: FlipMode = FlipMode.HORIZONTAL

        self._add_input(InputPort("image", set(IMAGE_TYPES)))
        self._add_output(OutputPort("image", set(IMAGE_TYPES)))

        self._apply_default_params()

    @property
    @override
    def params(self) -> list[NodeParam]:
        return [
            NodeParam(
                "mode",
                NodeParamType.ENUM,
                {"default": FlipMode.HORIZONTAL, "enum": FlipMode},
            ),
        ]

    @property
    def mode(self) -> FlipMode:
        return self._mode

    @mode.setter
    def mode(self, value: int | FlipMode) -> None:
        try:
            self._mode = FlipMode(value)
        except ValueError as e:
            raise ValueError(
                f"mode must be one of {[m.value for m in FlipMode]} "
                f"(got {value!r})"
            ) from e

    @override
    def process_impl(self) -> None:
        in_data = self.inputs[0].data
        flipped = cv2.flip(in_data.image, int(self._mode))
        self.outputs[0].send(in_data.with_image(flipped))

from __future__ import annotations

import cv2
import numpy as np
from typing_extensions import override

from core.io_data import IMAGE_TYPES, IoDataType
from core.node_base import NodeBase, NodeParamType
from core.port import InputPort, OutputPort


class Shift(NodeBase):
    """Translate an image by integer pixel offsets.

    Uses ``cv2.warpAffine`` with a pure translation matrix so that the
    output canvas keeps the input's width and height — pixels shifted
    outside the frame are dropped and exposed areas are filled with
    black (OpenCV's default border). Ported from the original OCVL
    ``ShiftProcessor``.
    """

    def __init__(self) -> None:
        super().__init__("Shift", section="Transform")
        self._offset_x: int = 0
        self._offset_y: int = 0

        self._add_input(InputPort("image", set(IMAGE_TYPES)))
        self._add_input(InputPort(
            "offset_x",
            {IoDataType.SCALAR},
            optional=True,
            default_value=0,
            metadata={"default": 0, "param_type": NodeParamType.INT},
        ))
        self._add_input(InputPort(
            "offset_y",
            {IoDataType.SCALAR},
            optional=True,
            default_value=0,
            metadata={"default": 0, "param_type": NodeParamType.INT},
        ))
        self._add_output(OutputPort("image", set(IMAGE_TYPES)))

        self._apply_default_params()

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def offset_x(self) -> int:
        return self._offset_x

    @offset_x.setter
    def offset_x(self, value: int) -> None:
        self._offset_x = int(value)

    @property
    def offset_y(self) -> int:
        return self._offset_y

    @offset_y.setter
    def offset_y(self, value: int) -> None:
        self._offset_y = int(value)

    # ── NodeBase interface ─────────────────────────────────────────────────────

    @override
    def process_impl(self) -> None:
        in_data = self.inputs[0].data
        image: np.ndarray = in_data.image
        h, w = image.shape[:2]
        matrix = np.float32([[1, 0, self._offset_x],
                             [0, 1, self._offset_y]])
        shifted = cv2.warpAffine(image, matrix, (w, h))
        self.outputs[0].send(in_data.with_image(shifted))

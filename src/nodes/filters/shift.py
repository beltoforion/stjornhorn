from __future__ import annotations

import cv2
import numpy as np
from typing_extensions import override

from core.io_data import IMAGE_TYPES
from core.node_base import NodeBase
from core.params import IntParam
from core.port import InputPort, OutputPort


class Shift(NodeBase):
    """Translate an image by integer pixel offsets.

    The output canvas keeps the input's width and height — pixels
    shifted outside the frame are dropped and exposed areas are
    filled with black.
    """

    offset_x = IntParam(
        0,
        unit="px",
        description=(
            "Horizontal shift in pixels. Positive moves right; "
            "exposed areas at the left edge are filled with black."
        ),
    )
    offset_y = IntParam(
        0,
        unit="px",
        description=(
            "Vertical shift in pixels. Positive moves down; "
            "exposed areas at the top edge are filled with black."
        ),
    )

    def __init__(self) -> None:
        super().__init__("Shift", section="Transform")
        self._add_input(InputPort("image", set(IMAGE_TYPES)))
        self._add_output(OutputPort("image", set(IMAGE_TYPES)))
        self._apply_default_params()

    @override
    def process_impl(self) -> None:
        in_data = self.inputs[0].data
        image: np.ndarray = in_data.image
        h, w = image.shape[:2]
        matrix = np.float32([[1, 0, self._offset_x],
                             [0, 1, self._offset_y]])
        shifted = cv2.warpAffine(image, matrix, (w, h))
        self.outputs[0].send(in_data.clone(payload=shifted))

from __future__ import annotations

import cv2
import numpy as np
from typing_extensions import override

from core.io_data import IMAGE_TYPES
from core.node_base import NodeBase
from core.params import OddIntParam
from core.port import InputPort, OutputPort


class Median(NodeBase):
    """Apply a median blur with a square kernel.

    ``size`` is the kernel side length in pixels (odd, ≥ 3). Accepts
    colour or greyscale and emits the same type.
    """

    size = OddIntParam(
        3,
        min=3,
        unit="px",
        description=(
            "Kernel side length in pixels. Odd, >= 3. Larger kernels "
            "remove more noise at the cost of fine detail."
        ),
    )

    def __init__(self) -> None:
        super().__init__("Median", section="Processing")
        self._add_input(InputPort("image", set(IMAGE_TYPES)))
        self._add_output(OutputPort("image", set(IMAGE_TYPES)))
        self._apply_default_params()

    @override
    def process_impl(self) -> None:
        in_data = self.inputs[0].data
        blurred = cv2.medianBlur(in_data.image, self._size)
        self.outputs[0].send(in_data.clone(payload=blurred))

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

    Wraps ``cv2.medianBlur``; the kernel ``size`` must be odd and ≥ 1
    — :class:`~core.params.OddIntParam` enforces both invariants so the
    UI spin-box can step in odd numbers and accept (then bump) even
    typed input. Accepts both colour (``IMAGE``) and greyscale
    (``IMAGE_GREY``) inputs and emits the same type on the output.
    """

    size = OddIntParam(
        3,
        min=1,
        unit="px",
        description=(
            "Kernel side length in pixels. Must be odd; even values "
            "are bumped up to the next odd integer. Larger kernels "
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

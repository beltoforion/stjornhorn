from __future__ import annotations

import cv2
from typing_extensions import override

from core.io_data import IMAGE_TYPES
from core.node_base import NodeBase
from core.params import FloatParam, OddIntParam
from core.port import InputPort, OutputPort


class GaussianBlur(NodeBase):
    """Smooth an image with an isotropic Gaussian kernel.

    ``ksize`` is the kernel side length in pixels (odd, ≥ 3).
    ``sigma`` is the standard deviation of the Gaussian; ``0`` derives
    it from the kernel size.
    """

    ksize = OddIntParam(
        5,
        min=3,
        unit="px",
        description=(
            "Kernel side length in pixels. Odd, >= 3. Larger kernels "
            "blur more strongly and run more slowly."
        ),
    )
    sigma = FloatParam(
        0.0,
        min=0.0,
        description=(
            "Standard deviation of the Gaussian. Set to 0 to derive "
            "it from the kernel size."
        ),
    )

    HEADER_ICON = "blur_on"

    def __init__(self) -> None:
        super().__init__("Gaussian Blur", section="Processing")
        self._add_input(InputPort("image", set(IMAGE_TYPES)))
        self._add_output(OutputPort("image", set(IMAGE_TYPES)))
        self._apply_default_params()

    @override
    def process_impl(self) -> None:
        in_data = self.inputs[0].data
        blurred = cv2.GaussianBlur(
            in_data.image,
            (self._ksize, self._ksize),
            self._sigma,
        )
        self.outputs[0].send(in_data.clone(payload=blurred))

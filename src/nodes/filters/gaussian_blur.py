from __future__ import annotations

import cv2
from typing_extensions import override

from core.io_data import IMAGE_TYPES
from core.node_base import NodeBase
from core.params import FloatParam, OddIntParam
from core.port import InputPort, OutputPort


class GaussianBlur(NodeBase):
    """Smooth an image with an isotropic Gaussian kernel.

    Wraps :func:`cv2.GaussianBlur`. ``ksize`` is the kernel side length
    in pixels; the OpenCV-required odd-only invariant is enforced by
    :class:`~core.params.OddIntParam` so even values are bumped up to
    the next odd integer. ``sigma`` is the standard deviation of the
    Gaussian; the OpenCV convention of ``sigma == 0`` "derive from
    kernel size" is preserved.
    """

    ksize = OddIntParam(
        5,
        min=1,
        unit="px",
        description=(
            "Kernel side length in pixels. Must be odd; even values "
            "are bumped up to the next odd integer. Larger kernels "
            "blur more strongly and run more slowly."
        ),
    )
    sigma = FloatParam(
        0.0,
        min=0.0,
        description=(
            "Standard deviation of the Gaussian. Set to 0 to derive "
            "it from the kernel size automatically (OpenCV's default)."
        ),
    )

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
        self.outputs[0].send(in_data.with_image(blurred))

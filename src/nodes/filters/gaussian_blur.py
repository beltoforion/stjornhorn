from __future__ import annotations

import cv2
from typing_extensions import override

from core.io_data import IMAGE_TYPES, IoDataType
from core.node_base import NodeBase, NodeParamType
from core.port import InputPort, OutputPort


class GaussianBlur(NodeBase):
    """Smooth an image with an isotropic Gaussian kernel.

    Wraps :func:`cv2.GaussianBlur`. ``ksize`` is the kernel side length
    in pixels (must be odd; even values are bumped up to the next odd
    integer the way :class:`Median` does it). ``sigma`` is the standard
    deviation of the Gaussian; the OpenCV convention of ``sigma == 0``
    "derive from kernel size" is preserved.
    """

    def __init__(self) -> None:
        super().__init__("Gaussian Blur", section="Processing")
        self._ksize: int   = 5
        self._sigma: float = 0.0

        self._add_input(InputPort("image", set(IMAGE_TYPES)))
        self._add_input(InputPort(
            "ksize",
            {IoDataType.SCALAR},
            optional=True,
            default_value=5,
            metadata={"default": 5, "param_type": NodeParamType.INT},
        ))
        self._add_input(InputPort(
            "sigma",
            {IoDataType.SCALAR},
            optional=True,
            default_value=0.0,
            metadata={"default": 0.0, "param_type": NodeParamType.FLOAT},
        ))
        self._add_output(OutputPort("image", set(IMAGE_TYPES)))

        self._apply_default_params()

    @property
    def ksize(self) -> int:
        return self._ksize

    @ksize.setter
    def ksize(self, value: int) -> None:
        v = int(value)
        if v < 1:
            raise ValueError(f"ksize must be >= 1 (got {v})")
        if v % 2 == 0:
            v += 1
        self._ksize = v

    @property
    def sigma(self) -> float:
        return self._sigma

    @sigma.setter
    def sigma(self, value: float) -> None:
        v = float(value)
        if v < 0.0:
            raise ValueError(f"sigma must be >= 0 (got {v})")
        self._sigma = v

    @override
    def process_impl(self) -> None:
        in_data = self.inputs[0].data
        blurred = cv2.GaussianBlur(
            in_data.image,
            (self._ksize, self._ksize),
            self._sigma,
        )
        self.outputs[0].send(in_data.with_image(blurred))

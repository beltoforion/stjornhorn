from __future__ import annotations

import numpy as np
from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase
from core.port import InputPort, OutputPort


class ImageToMatrix(NodeBase):
    """Reinterpret a greyscale image as a 2-D MATRIX payload.

    Bridges :data:`IoDataType.IMAGE_GREY` → :data:`IoDataType.MATRIX`
    so a spatial-domain greyscale image can flow into MATRIX-only
    consumers — typically :class:`MatrixAdd` between :class:`Fft2D`
    and :class:`InverseFft2D` to inject a real-valued perturbation
    directly into a spectrum. Pixel values are cast to ``float64``;
    no FFT, no normalisation, no shape change.

    For the inverse transform to stay real, the perturbation must
    be Hermitian. A real, point-symmetric image (``f(x,y) =
    f(-x,-y)`` about its centre) is automatically Hermitian when
    used as a spectrum addend, which is the building block of
    stealthy frequency-domain watermarking.
    """

    HEADER_ICON = "grid_view"

    def __init__(self) -> None:
        super().__init__("Image To Matrix", section="Frequency")
        self._add_input(InputPort("image", {IoDataType.IMAGE_GREY}))
        self._add_output(OutputPort("matrix", {IoDataType.MATRIX}))

    @override
    def process_impl(self) -> None:
        in_data = self.inputs[0].data
        image: np.ndarray = in_data.image
        if image.ndim != 2:
            raise ValueError(
                f"ImageToMatrix expects a single-channel image, got shape {image.shape}"
            )
        matrix = image.astype(np.float64)
        self.outputs[0].send(IoData.from_matrix(matrix, meta=in_data.meta))

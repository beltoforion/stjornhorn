from __future__ import annotations

import numpy as np
from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase
from core.params import FloatParam
from core.port import InputPort, OutputPort


class MatrixAdd(NodeBase):
    """Linear combination of two matrices: ``out = a + weight * b``.

    Both inputs must have identical shape; mismatched shapes raise
    rather than auto-resize, since a matrix here is typically a
    spectrum where dimensions carry frequency-axis meaning. Dtypes
    are promoted by numpy's usual rules so a real + complex mix
    (e.g. plain matrix + FFT spectrum) just works.

    Built for the :class:`Fft2D` → :class:`InverseFft2D` corridor:
    drop a :class:`BandpassMask` on a second spectrum and feed both
    here with a small ``weight`` to embed an invisible perturbation
    of ``a`` — the basis of frequency-domain watermarking.
    """

    weight = FloatParam(
        1.0,
        description=(
            "Scalar multiplier applied to the second input before "
            "summing. 1.0 = plain addition; small values "
            "(e.g. 0.05) embed ``b`` as an imperceptible "
            "perturbation of ``a``."
        ),
    )

    HEADER_ICON = "add"

    def __init__(self) -> None:
        super().__init__("Matrix Add", section="Frequency")
        self._add_input(InputPort("a", {IoDataType.MATRIX}))
        self._add_input(InputPort("b", {IoDataType.MATRIX}))
        self._add_output(OutputPort("result", {IoDataType.MATRIX}))
        self._apply_default_params()

    @override
    def process_impl(self) -> None:
        a_data = self.inputs[0].data
        b_data = self.inputs[1].data
        a: np.ndarray = a_data.payload
        b: np.ndarray = b_data.payload
        if a.shape != b.shape:
            raise ValueError(
                f"MatrixAdd: shape mismatch {a.shape} vs {b.shape}"
            )
        result = a + (self._weight * b)
        self.outputs[0].send(IoData.from_matrix(result, meta=a_data.meta))

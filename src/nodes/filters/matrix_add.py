from __future__ import annotations

import numpy as np
from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase
from core.params import FloatParam
from core.port import InputPort, OutputPort


class MatrixAdd(NodeBase):
    """Linear combination of two matrices: ``out = base + weight * addend``.

    Both inputs must have identical shape; mismatched shapes raise
    rather than auto-resize, since a matrix here is typically a
    spectrum where dimensions carry frequency-axis meaning. Dtypes
    are promoted by numpy's usual rules so a real + complex mix
    (e.g. plain matrix + FFT spectrum) just works.

    Built for the :class:`Fft2D` → :class:`InverseFft2D` corridor:
    drop a :class:`BandpassMask` on a second spectrum and feed both
    here with a small ``weight`` to embed an imperceptible
    perturbation of ``base`` — the basis of frequency-domain
    watermarking.
    """

    weight = FloatParam(
        1.0,
        description=(
            "Scalar multiplier applied to ``addend`` before summing. "
            "1.0 = plain addition; small values (e.g. 0.05) embed "
            "``addend`` as an imperceptible perturbation of ``base``."
        ),
    )

    HEADER_ICON = "add"

    def __init__(self) -> None:
        super().__init__("Matrix Add", section="Frequency")
        self._add_input(InputPort("base", {IoDataType.MATRIX}))
        self._add_input(InputPort("addend", {IoDataType.MATRIX}))
        self._add_output(OutputPort("result", {IoDataType.MATRIX}))
        self._apply_default_params()

    @override
    def process_impl(self) -> None:
        base_data = self.inputs[0].data
        addend_data = self.inputs[1].data
        base: np.ndarray = base_data.payload
        addend: np.ndarray = addend_data.payload
        if base.shape != addend.shape:
            raise ValueError(
                f"MatrixAdd: shape mismatch {base.shape} vs {addend.shape}"
            )
        result = base + (self._weight * addend)
        self.outputs[0].send(IoData.from_matrix(result, meta=base_data.meta))

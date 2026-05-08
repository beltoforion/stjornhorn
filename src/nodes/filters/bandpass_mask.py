from __future__ import annotations

import numpy as np
from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase
from core.params import ClampedFloatParam
from core.port import InputPort, OutputPort


class BandpassMask(NodeBase):
    """Annular band-pass mask on an fftshifted spectrum.

    Zeroes coefficients outside the radius range
    ``[radius_low, radius_high]`` (inclusive). Radius is normalised
    so 0 = DC (centre of the fftshifted spectrum) and 1 = the
    corner — ``0.5`` lands roughly on the diagonal half-Nyquist.

    Designed for the output of :class:`Fft2D` (DC at centre). The
    mask is centro-symmetric by construction, so a real-valued
    image's spectrum stays Hermitian after masking and
    :class:`InverseFft2D` produces a real image.
    """

    radius_low = ClampedFloatParam(
        0.05,
        min=0.0,
        max=1.0,
        description=(
            "Inner radius of the pass band, normalised to "
            "[0, 1] (0 = DC). Coefficients below this radius "
            "are zeroed."
        ),
    )
    radius_high = ClampedFloatParam(
        0.25,
        min=0.0,
        max=1.0,
        description=(
            "Outer radius of the pass band, normalised to "
            "[0, 1] (1 = spectrum corner). Coefficients above "
            "this radius are zeroed."
        ),
    )

    HEADER_ICON = "tune"

    def __init__(self) -> None:
        super().__init__("Bandpass Mask", section="Frequency")
        self._add_input(InputPort("spectrum", {IoDataType.MATRIX}))
        self._add_output(OutputPort("spectrum", {IoDataType.MATRIX}))
        self._apply_default_params()

    @override
    def process_impl(self) -> None:
        in_data = self.inputs[0].data
        spectrum: np.ndarray = in_data.payload
        if spectrum.ndim != 2:
            raise ValueError(
                f"BandpassMask expects a 2-D spectrum, got shape {spectrum.shape}"
            )

        r_lo = float(self._radius_low)
        r_hi = float(self._radius_high)
        if r_lo > r_hi:
            raise ValueError(
                f"BandpassMask: radius_low {r_lo} > radius_high {r_hi}"
            )

        h, w = spectrum.shape
        cy, cx = h / 2.0, w / 2.0
        ys = np.arange(h, dtype=np.float64) - cy
        xs = np.arange(w, dtype=np.float64) - cx
        yy, xx = np.meshgrid(ys, xs, indexing="ij")
        r_norm = np.sqrt(yy * yy + xx * xx) / np.sqrt(cx * cx + cy * cy)

        mask = (r_norm >= r_lo) & (r_norm <= r_hi)
        masked = spectrum * mask
        self.outputs[0].send(IoData.from_matrix(masked, meta=in_data.meta))

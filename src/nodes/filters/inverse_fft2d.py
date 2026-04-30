from __future__ import annotations

import numpy as np
from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase
from core.port import InputPort, OutputPort


class InverseFft2D(NodeBase):
    """Compute the inverse 2-D discrete Fourier transform.

    Inverse of :class:`Fft2D`. Expects the fftshifted complex
    spectrum on ``spectrum`` and emits a uint8
    :data:`IoDataType.IMAGE_GREY` on ``image``. Forms a pixel-exact
    round trip with :class:`Fft2D` on a greyscale uint8 input.
    """

    def __init__(self) -> None:
        super().__init__("Inverse FFT 2D", section="Frequency")
        self._add_input(InputPort("spectrum", {IoDataType.MATRIX}))
        self._add_output(OutputPort("image", {IoDataType.IMAGE_GREY}))

    @override
    def process_impl(self) -> None:
        spectrum: np.ndarray = self.inputs[0].data.payload
        if spectrum.ndim != 2:
            raise ValueError(
                f"InverseFft2D expects a 2-D spectrum, got shape {spectrum.shape}"
            )

        recon = np.fft.ifft2(np.fft.ifftshift(spectrum)).real
        np.round(recon, out=recon)
        np.clip(recon, 0.0, 255.0, out=recon)
        image = recon.astype(np.uint8, copy=False)
        self.outputs[0].send(IoData.from_greyscale(image))

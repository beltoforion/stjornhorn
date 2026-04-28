from __future__ import annotations

import cv2
import numpy as np
from typing_extensions import override

from core.io_data import IMAGE_TYPES, IoData, IoDataType
from core.node_base import NodeBase
from core.params import IntParam, OddIntParam
from core.port import InputPort, OutputPort


class AdaptiveGaussianThreshold(NodeBase):
    """Adaptive Gaussian binary threshold.

    Wraps ``cv2.adaptiveThreshold`` with
    ``ADAPTIVE_THRESH_GAUSSIAN_C`` and ``THRESH_BINARY``. ``block_size``
    must be odd and >= 3 — :class:`~core.params.OddIntParam` enforces
    the odd-only invariant; the ``min=3`` check catches the lower bound
    after the even→odd bump (so 2 → 3 is accepted).

    Accepts colour or greyscale inputs; 3-channel inputs are internally
    converted to greyscale first. The output is always a single-channel
    binary :data:`IoDataType.IMAGE_GREY` payload.
    """

    block_size = OddIntParam(
        101,
        min=3,
        unit="px",
        description=(
            "Side length of the neighbourhood used to compute the "
            "local threshold. Must be odd and >= 3; even values "
            "are bumped up to the next odd integer."
        ),
    )
    c = IntParam(
        -32,
        description=(
            "Constant subtracted from the local weighted mean. "
            "Negative values bias toward classifying pixels as "
            "white; positive values bias toward black."
        ),
    )

    def __init__(self) -> None:
        super().__init__("Adaptive Gaussian Threshold", section="Processing")
        self._add_input(InputPort("image", set(IMAGE_TYPES)))
        self._add_output(OutputPort("image", {IoDataType.IMAGE_GREY}))
        self._apply_default_params()

    @override
    def process_impl(self) -> None:
        image: np.ndarray = self.inputs[0].data.image

        if image.ndim == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        th = cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            self._block_size,
            self._c,
        )
        self.outputs[0].send(IoData.from_greyscale(th))

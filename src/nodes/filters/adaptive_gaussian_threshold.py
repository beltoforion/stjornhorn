from __future__ import annotations

import cv2
import numpy as np
from typing_extensions import override

from core.io_data import IMAGE_TYPES, IoData, IoDataType
from core.node_base import NodeBase, NodeParam, NodeParamType
from core.port import InputPort, OutputPort


class AdaptiveGaussianThreshold(NodeBase):
    """Adaptive Gaussian binary threshold.

    Wraps ``cv2.adaptiveThreshold`` with
    ``ADAPTIVE_THRESH_GAUSSIAN_C`` and ``THRESH_BINARY``. ``block_size``
    must be odd and > 1; ``c`` is the constant subtracted from the
    weighted mean. Ported from the original OCVL
    ``AdaptiveGuaussianThresholdProcessor`` [sic].

    Accepts colour or greyscale inputs; 3-channel inputs are internally
    converted to greyscale first. The output is always a single-channel
    binary :data:`IoDataType.IMAGE_GREY` payload.
    """

    def __init__(self) -> None:
        super().__init__("Adaptive Gaussian Threshold", section="Processing")
        self._block_size: int = 101
        self._c: int = -32

        self._add_input(InputPort("image", set(IMAGE_TYPES)))
        self._add_output(OutputPort("image", {IoDataType.IMAGE_GREY}))

        self._apply_default_params()

    # ── Parameters ─────────────────────────────────────────────────────────────

    @property
    @override
    def params(self) -> list[NodeParam]:
        return [
            NodeParam("block_size", NodeParamType.INT, {"default": 101}),
            NodeParam("c",          NodeParamType.INT, {"default": -32}),
        ]

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def block_size(self) -> int:
        return self._block_size

    @block_size.setter
    def block_size(self, value: int) -> None:
        v = int(value)
        if v < 3:
            raise ValueError(f"block_size must be >= 3 (got {v})")
        if v % 2 == 0:
            # cv2.adaptiveThreshold requires odd — coerce like Median does.
            v += 1
        self._block_size = v

    @property
    def c(self) -> int:
        return self._c

    @c.setter
    def c(self, value: int) -> None:
        self._c = int(value)

    # ── NodeBase interface ─────────────────────────────────────────────────────

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

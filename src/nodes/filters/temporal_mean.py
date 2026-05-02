from __future__ import annotations

import numpy as np
from typing_extensions import override

from core.io_data import IMAGE_TYPES
from core.node_base import NodeBase
from core.params import IntParam
from core.port import InputPort, OutputPort


class TemporalMean(NodeBase):
    """Rolling per-pixel arithmetic mean over the last ``window`` frames.

    Reduces additive Gaussian-style noise on a static scene. While
    the buffer fills, the mean of however many frames have arrived
    so far is emitted. Shape changes mid-run flush the buffer.
    """

    window = IntParam(
        5,
        min=2,
        unit="frames",
        description=(
            "Number of recent frames averaged per output. >= 2. "
            "Larger values denoise more aggressively but blur any "
            "motion in the scene."
        ),
    )

    HEADER_ICON = "analytics"

    def __init__(self) -> None:
        super().__init__("Temporal Mean", section="Temporal")
        self._buffer: list[np.ndarray] = []
        self._add_input(InputPort("image", set(IMAGE_TYPES)))
        self._add_output(OutputPort("image", set(IMAGE_TYPES)))
        self._apply_default_params()

    @override
    def _before_run_impl(self) -> None:
        super()._before_run_impl()
        self._buffer = []

    @override
    def process_impl(self) -> None:
        in_data = self.inputs[0].data
        image: np.ndarray = in_data.image

        if self._buffer and self._buffer[0].shape != image.shape:
            self._buffer.clear()

        self._buffer.append(image)
        while len(self._buffer) > self._window:
            self._buffer.pop(0)

        # Float intermediate to avoid uint8 overflow on the sum, cast back
        # to the input dtype so downstream nodes get the type they expect.
        stack = np.stack(self._buffer, axis=0).astype(np.float32)
        mean = stack.mean(axis=0).astype(image.dtype)
        self.outputs[0].send(in_data.clone(payload=mean))

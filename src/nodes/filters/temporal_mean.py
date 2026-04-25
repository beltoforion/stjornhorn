from __future__ import annotations

import numpy as np
from typing_extensions import override

from core.io_data import IMAGE_TYPES
from core.node_base import NodeBase, NodeParam, NodeParamType
from core.port import InputPort, OutputPort


class TemporalMean(NodeBase):
    """Rolling per-pixel arithmetic mean over the last ``window`` frames.

    Reduces additive Gaussian-style noise on a static scene. Maintains
    a buffer of the most recent ``window`` frames and emits their
    per-pixel mean each tick. Until the buffer is full, the mean of
    however many frames have been seen so far is emitted (so the very
    first frame passes through unchanged).

    Shape changes mid-run (e.g. an upstream Crop param edited live)
    flush the buffer rather than raising — the next emitted frame is
    just the new input.
    """

    def __init__(self) -> None:
        super().__init__("Temporal Mean", section="Temporal")
        self._window: int = 5
        self._buffer: list[np.ndarray] = []

        self._add_input(InputPort("image", set(IMAGE_TYPES)))
        self._add_output(OutputPort("image", set(IMAGE_TYPES)))

        self._apply_default_params()

    @property
    @override
    def params(self) -> list[NodeParam]:
        return [
            NodeParam("window", NodeParamType.INT, {"default": 5}),
        ]

    @property
    def window(self) -> int:
        return self._window

    @window.setter
    def window(self, value: int) -> None:
        v = int(value)
        if v < 1:
            raise ValueError(f"window must be >= 1 (got {v})")
        self._window = v

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
        self.outputs[0].send(in_data.with_image(mean))

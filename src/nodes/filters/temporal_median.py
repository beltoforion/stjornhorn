from __future__ import annotations

import numpy as np
from typing_extensions import override

from core.io_data import IMAGE_TYPES
from core.node_base import NodeBase
from core.params import IntParam
from core.port import InputPort, OutputPort


class TemporalMedian(NodeBase):
    """Rolling per-pixel median over the last ``window`` frames.

    Strong against transient outliers (single-frame spikes, flicker,
    salt-and-pepper noise) without the smearing a mean would produce.
    While the buffer fills, the median over however many frames have
    arrived so far is emitted. Shape changes mid-run flush the buffer.
    """

    window = IntParam(
        5,
        min=2,
        unit="frames",
        description=(
            "Number of recent frames whose per-pixel median is "
            "emitted. >= 2."
        ),
    )

    HEADER_ICON = "analytics"

    def __init__(self) -> None:
        super().__init__("Temporal Median", section="Temporal")
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

        # np.median always returns float64 — cast back to the input
        # dtype so downstream nodes get the type they expect.
        stack = np.stack(self._buffer, axis=0)
        median = np.median(stack, axis=0).astype(image.dtype)
        self.outputs[0].send(in_data.clone(payload=median))

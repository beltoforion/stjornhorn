from __future__ import annotations

import numpy as np
from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase
from core.params import FloatParam
from core.port import InputPort, OutputPort


class Clamp(NodeBase):
    """Clamp a SCALAR stream to ``[min_value, max_value]``.

    Each frame the input value is constrained to the configured range:
    values below ``min_value`` become ``min_value``, values above
    ``max_value`` become ``max_value``, and values inside the range
    pass through unchanged.

    If ``min_value > max_value`` the bounds are swapped before
    clamping — the alternative (raising) would be hostile in a UI
    where the user types one bound at a time and may transiently
    invert the range.
    """

    min_value = FloatParam(
        0.0,
        description="Lower bound. Values below this are clipped up to it.",
    )
    max_value = FloatParam(
        1.0,
        description=(
            "Upper bound. Values above this are clipped down to it. "
            "If the upper bound ends up below the lower bound the "
            "two are swapped so the range is always usable."
        ),
    )

    def __init__(self) -> None:
        super().__init__("Clamp", section="Math")
        self._add_input(InputPort("value", {IoDataType.SCALAR}))
        self._add_output(OutputPort("value", {IoDataType.SCALAR}))
        self._apply_default_params()

    @override
    def process_impl(self) -> None:
        v: np.ndarray = self.inputs[0].data.payload
        lo, hi = self._min_value, self._max_value
        if lo > hi:
            lo, hi = hi, lo
        clamped = np.clip(v, lo, hi)
        self.outputs[0].send(IoData.from_scalar(clamped))

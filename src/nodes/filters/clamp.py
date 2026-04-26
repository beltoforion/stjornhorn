from __future__ import annotations

import numpy as np
from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase, NodeParamType
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

    def __init__(self) -> None:
        super().__init__("Clamp", section="Math")
        self._min_value: float = 0.0
        self._max_value: float = 1.0

        self._add_input(InputPort("value", {IoDataType.SCALAR}))
        self._add_input(InputPort(
            "min_value",
            {IoDataType.SCALAR},
            optional=True,
            default_value=0.0,
            metadata={"default": 0.0, "param_type": NodeParamType.FLOAT},
        ))
        self._add_input(InputPort(
            "max_value",
            {IoDataType.SCALAR},
            optional=True,
            default_value=1.0,
            metadata={"default": 1.0, "param_type": NodeParamType.FLOAT},
        ))
        self._add_output(OutputPort("value", {IoDataType.SCALAR}))

        self._apply_default_params()

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def min_value(self) -> float:
        return self._min_value

    @min_value.setter
    def min_value(self, value: float) -> None:
        self._min_value = float(value)

    @property
    def max_value(self) -> float:
        return self._max_value

    @max_value.setter
    def max_value(self, value: float) -> None:
        self._max_value = float(value)

    # ── NodeBase interface ─────────────────────────────────────────────────────

    @override
    def process_impl(self) -> None:
        v: np.ndarray = self.inputs[0].data.payload
        lo, hi = self._min_value, self._max_value
        if lo > hi:
            lo, hi = hi, lo
        clamped = np.clip(v, lo, hi)
        self.outputs[0].send(IoData.from_scalar(clamped))

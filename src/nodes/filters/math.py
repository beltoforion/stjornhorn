from __future__ import annotations

from enum import IntEnum

import numpy as np
from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase, NodeParam, NodeParamType
from core.port import InputPort, OutputPort


class MathOp(IntEnum):
    """Binary arithmetic operation applied by :class:`Math`.

    Backed by :class:`IntEnum` so the integer value persists in saved
    flows and round-trips through the ``ENUM`` param widget.
    """
    ADD = 0
    SUB = 1
    MUL = 2
    DIV = 3
    MIN = 4
    MAX = 5


class Math(NodeBase):
    """Apply a binary arithmetic op to two SCALAR streams.

    Both inputs are required. Each frame, the configured ``op`` is
    applied to ``(a, b)`` and the result is emitted as a SCALAR.
    Numpy 0-d arithmetic is used directly, so dtype follows numpy's
    promotion rules: ``int + int → int``, ``int / int → float``,
    ``float + int → float``.

    Pair with a :class:`~nodes.sources.constant_value.ConstantValue`
    (reactive, one-shot) on one input and a streaming source like
    :class:`~nodes.sources.value_source.ValueSource` on the other to
    transform every value in a stream by a fixed offset/factor — e.g.
    ramp 0..359 multiplied by 0.5 to get 0..180 in half-degree steps.
    """

    def __init__(self) -> None:
        super().__init__("Math", section="Math")
        self._op: MathOp = MathOp.ADD

        self._add_input(InputPort("a", {IoDataType.SCALAR}))
        self._add_input(InputPort("b", {IoDataType.SCALAR}))
        self._add_output(OutputPort("result", {IoDataType.SCALAR}))

        self._apply_default_params()

    # ── Parameters ─────────────────────────────────────────────────────────────

    @property
    @override
    def params(self) -> list[NodeParam]:
        return [
            NodeParam("op", NodeParamType.ENUM, {"default": MathOp.ADD, "enum": MathOp}),
        ]

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def op(self) -> MathOp:
        return self._op

    @op.setter
    def op(self, value: int | MathOp) -> None:
        try:
            self._op = MathOp(value)
        except ValueError as e:
            raise ValueError(
                f"op must be one of {[m.value for m in MathOp]} (got {value!r})"
            ) from e

    # ── NodeBase interface ─────────────────────────────────────────────────────

    @override
    def process_impl(self) -> None:
        a: np.ndarray = self.inputs[0].data.payload
        b: np.ndarray = self.inputs[1].data.payload

        if self._op is MathOp.ADD:
            result = a + b
        elif self._op is MathOp.SUB:
            result = a - b
        elif self._op is MathOp.MUL:
            result = a * b
        elif self._op is MathOp.DIV:
            # Use np.true_divide so int/int returns float instead of
            # raising ZeroDivisionError on divide-by-zero (numpy emits a
            # warning + inf/nan, which propagates downstream as a value).
            result = np.true_divide(a, b)
        elif self._op is MathOp.MIN:
            result = np.minimum(a, b)
        else:  # MathOp.MAX
            result = np.maximum(a, b)

        self.outputs[0].send(IoData.from_scalar(result))

"""Unit tests for the Math binary-op node."""
from __future__ import annotations

import numpy as np
import pytest

from core.io_data import IoData, IoDataType
from core.port import InputPort, OutputPort
from nodes.filters.math import Math, MathOp


def _wire(node: Math) -> tuple[OutputPort, OutputPort, list[IoData]]:
    up_a = OutputPort("a_up", {IoDataType.SCALAR})
    up_b = OutputPort("b_up", {IoDataType.SCALAR})
    up_a.connect(node.inputs[0])
    up_b.connect(node.inputs[1])

    captured: list[IoData] = []
    sink = InputPort("sink", {IoDataType.SCALAR})
    sink.set_on_state_changed(
        lambda: captured.append(sink.data) if sink.has_data else None
    )
    node.outputs[0].connect(sink)
    return up_a, up_b, captured


def _drive(up_a: OutputPort, up_b: OutputPort, a, b) -> None:
    up_a.send(IoData.from_scalar(a))
    up_b.send(IoData.from_scalar(b))


def test_add_emits_sum() -> None:
    node = Math()
    node.op = MathOp.ADD
    up_a, up_b, captured = _wire(node)

    node.before_run()
    _drive(up_a, up_b, 3, 4)

    assert len(captured) == 1
    assert captured[0].type is IoDataType.SCALAR
    assert int(captured[0].payload.item()) == 7


def test_sub_emits_difference() -> None:
    node = Math()
    node.op = MathOp.SUB
    up_a, up_b, captured = _wire(node)

    node.before_run()
    _drive(up_a, up_b, 10, 4)

    assert int(captured[0].payload.item()) == 6


def test_mul_emits_product() -> None:
    node = Math()
    node.op = MathOp.MUL
    up_a, up_b, captured = _wire(node)

    node.before_run()
    _drive(up_a, up_b, 6, 7)

    assert int(captured[0].payload.item()) == 42


def test_div_promotes_int_inputs_to_float() -> None:
    """numpy true_divide always returns float, so 6/2 = 3.0 not 3.
    This avoids surprises when downstream code assumes the dtype."""
    node = Math()
    node.op = MathOp.DIV
    up_a, up_b, captured = _wire(node)

    node.before_run()
    _drive(up_a, up_b, 6, 2)

    value = captured[0].payload.item()
    assert value == 3.0
    assert isinstance(value, float)


def test_div_by_zero_yields_inf_not_exception() -> None:
    """np.true_divide on int/0 emits a warning and produces inf rather
    than raising, so the flow doesn't crash on a transient bad value."""
    node = Math()
    node.op = MathOp.DIV
    up_a, up_b, captured = _wire(node)

    node.before_run()
    with np.errstate(divide="ignore", invalid="ignore"):
        _drive(up_a, up_b, 5, 0)

    assert np.isinf(captured[0].payload.item())


def test_min_picks_lower() -> None:
    node = Math()
    node.op = MathOp.MIN
    up_a, up_b, captured = _wire(node)

    node.before_run()
    _drive(up_a, up_b, 5, 3)

    assert int(captured[0].payload.item()) == 3


def test_max_picks_higher() -> None:
    node = Math()
    node.op = MathOp.MAX
    up_a, up_b, captured = _wire(node)

    node.before_run()
    _drive(up_a, up_b, 5, 3)

    assert int(captured[0].payload.item()) == 5


def test_op_setter_accepts_int() -> None:
    """Flow-load passes the persisted int back through setattr — must
    coerce to enum without raising."""
    node = Math()
    node.op = 2
    assert node.op is MathOp.MUL


def test_op_setter_rejects_unknown_value() -> None:
    node = Math()
    with pytest.raises(ValueError, match="op must be one of"):
        node.op = 99


def test_streams_per_frame_when_both_inputs_arrive() -> None:
    """Math fires once both a and b have data — multi-frame stream."""
    node = Math()
    node.op = MathOp.ADD
    up_a, up_b, captured = _wire(node)

    node.before_run()
    for av, bv in [(1, 10), (2, 20), (3, 30)]:
        _drive(up_a, up_b, av, bv)

    assert [int(d.payload.item()) for d in captured] == [11, 22, 33]


def test_input_types_restricted_to_scalar() -> None:
    """Math's inputs only declare SCALAR — an upstream IMAGE port
    can't connect, so type errors surface at link time."""
    node = Math()
    img_up = OutputPort("img", {IoDataType.IMAGE})
    assert img_up.can_connect(node.inputs[0]) is False
    assert img_up.can_connect(node.inputs[1]) is False

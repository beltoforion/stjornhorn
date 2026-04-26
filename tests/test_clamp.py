"""Unit tests for the Clamp scalar node."""
from __future__ import annotations

from core.io_data import IoData, IoDataType
from core.port import InputPort, OutputPort
from nodes.filters.clamp import Clamp


def _wire(node: Clamp) -> tuple[OutputPort, list[IoData]]:
    up = OutputPort("up", {IoDataType.SCALAR})
    up.connect(node.inputs[0])
    captured: list[IoData] = []
    sink = InputPort("sink", {IoDataType.SCALAR})
    sink.set_on_state_changed(
        lambda: captured.append(sink.data) if sink.has_data else None
    )
    node.outputs[0].connect(sink)
    return up, captured


def test_clamp_passes_value_inside_range_unchanged() -> None:
    node = Clamp()
    node.min_value = 0
    node.max_value = 100
    up, captured = _wire(node)

    node.before_run()
    up.send(IoData.from_scalar(42))

    assert captured[0].type is IoDataType.SCALAR
    assert int(captured[0].payload.item()) == 42


def test_clamp_caps_value_above_max() -> None:
    node = Clamp()
    node.min_value = 0
    node.max_value = 100
    up, captured = _wire(node)

    node.before_run()
    up.send(IoData.from_scalar(250))

    assert int(captured[0].payload.item()) == 100


def test_clamp_floors_value_below_min() -> None:
    node = Clamp()
    node.min_value = 0
    node.max_value = 100
    up, captured = _wire(node)

    node.before_run()
    up.send(IoData.from_scalar(-50))

    assert int(captured[0].payload.item()) == 0


def test_clamp_swaps_inverted_bounds() -> None:
    """Setting min > max could be a transient UI state — clamp swaps
    so the result is still well-defined rather than raising."""
    node = Clamp()
    node.min_value = 100
    node.max_value = 0  # inverted
    up, captured = _wire(node)

    node.before_run()
    for v in (-50, 50, 250):
        up.send(IoData.from_scalar(v))

    # Effective range is [0, 100] after the swap.
    assert [int(d.payload.item()) for d in captured] == [0, 50, 100]


def test_clamp_on_float_preserves_float() -> None:
    node = Clamp()
    node.min_value = 0.0
    node.max_value = 1.0
    up, captured = _wire(node)

    node.before_run()
    up.send(IoData.from_scalar(0.7))

    value = captured[0].payload.item()
    assert isinstance(value, float)
    assert value == 0.7

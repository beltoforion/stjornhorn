"""Unit tests for the ConstantValue source node."""
from __future__ import annotations

from core.io_data import IoData, IoDataType
from core.port import InputPort
from nodes.sources.constant_value import ConstantValue


def _wire_capture(node: ConstantValue) -> list[IoData]:
    captured: list[IoData] = []
    sink = InputPort("sink", {IoDataType.SCALAR})
    sink.set_on_state_changed(
        lambda: captured.append(sink.data) if sink.has_data else None
    )
    node.outputs[0].connect(sink)
    return captured


def test_emits_configured_value_once() -> None:
    node = ConstantValue()
    node.value = 7.5
    captured = _wire_capture(node)

    node.before_run()
    node.process_impl()

    assert len(captured) == 1
    assert captured[0].type is IoDataType.SCALAR
    assert captured[0].payload.item() == 7.5


def test_default_value_is_zero() -> None:
    node = ConstantValue()
    captured = _wire_capture(node)

    node.before_run()
    node.process_impl()

    assert captured[0].payload.item() == 0.0


def test_is_reactive() -> None:
    """Reactive sources auto-finish their outputs after start() so the
    value latches on streaming consumers — the property must be True
    or this source won't pair correctly with streaming sources."""
    assert ConstantValue().is_reactive is True


def test_value_setter_coerces_to_float() -> None:
    node = ConstantValue()
    node.value = 42  # int
    assert isinstance(node.value, float)
    assert node.value == 42.0

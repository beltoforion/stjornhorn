"""Unit tests for the ValueSource counter node."""
from __future__ import annotations

from core.io_data import IoData, IoDataType
from core.port import InputPort
from nodes.sources.value_source import ValueSource


def _wire_capture(node: ValueSource) -> list[IoData]:
    captured: list[IoData] = []
    sink = InputPort("sink", {IoDataType.SCALAR})
    sink.set_on_state_changed(
        lambda: captured.append(sink.data) if sink.has_data else None
    )
    node.outputs[0].connect(sink)
    return captured


def test_emits_scalar_iodata_per_frame() -> None:
    node = ValueSource()
    node.min_value = 0
    node.max_value = 4
    captured = _wire_capture(node)

    node.before_run()
    node.process_impl()

    assert len(captured) == 5
    assert all(d.type is IoDataType.SCALAR for d in captured)
    assert [int(d.payload.item()) for d in captured] == [0, 1, 2, 3, 4]


def test_default_range_is_zero_to_ninetynine() -> None:
    node = ValueSource()
    captured = _wire_capture(node)

    node.before_run()
    node.process_impl()

    assert len(captured) == 100
    assert int(captured[0].payload.item()) == 0
    assert int(captured[-1].payload.item()) == 99


def test_unit_multiplier_emits_int() -> None:
    """multiplier == 1.0 keeps the payload integer-valued so a Display
    label reads '42' rather than '42.0'."""
    node = ValueSource()
    node.min_value = 1
    node.max_value = 3
    node.multiplier = 1.0
    captured = _wire_capture(node)

    node.before_run()
    node.process_impl()

    for d in captured:
        # numpy 0-d int arrays expose .item() as a Python int
        assert isinstance(d.payload.item(), int)


def test_non_unit_multiplier_emits_float() -> None:
    node = ValueSource()
    node.min_value = 0
    node.max_value = 3
    node.multiplier = 0.5
    captured = _wire_capture(node)

    node.before_run()
    node.process_impl()

    values = [d.payload.item() for d in captured]
    assert values == [0.0, 0.5, 1.0, 1.5]
    assert all(isinstance(v, float) for v in values)


def test_loop_repeats_range_bounded_cycles() -> None:
    """loop=True cycles the range a bounded number of times so the
    flow runner (which has no cancel mechanism) still terminates."""
    node = ValueSource()
    node.min_value = 0
    node.max_value = 2
    node.loop = True
    captured = _wire_capture(node)

    node.before_run()
    node.process_impl()

    expected_per_cycle = [0, 1, 2]
    assert len(captured) == len(expected_per_cycle) * ValueSource._LOOP_CYCLES
    # First and last cycle both go 0,1,2 — wraparound is observable.
    head = [int(d.payload.item()) for d in captured[:3]]
    tail = [int(d.payload.item()) for d in captured[-3:]]
    assert head == expected_per_cycle
    assert tail == expected_per_cycle


def test_inverted_range_emits_nothing() -> None:
    """max_value < min_value is treated as an empty range — no values, no error."""
    node = ValueSource()
    node.min_value = 10
    node.max_value = 5
    captured = _wire_capture(node)

    node.before_run()
    node.process_impl()

    assert captured == []


def test_params_round_trip_through_setattr() -> None:
    """The setattr/getattr path used by widgets and flow-load must
    still work — verifies the property setters coerce types."""
    node = ValueSource()
    setattr(node, "min_value", "5")        # widget hands strings sometimes
    setattr(node, "max_value", 12.0)
    setattr(node, "multiplier", 2)
    setattr(node, "loop", 1)

    assert node.min_value == 5
    assert node.max_value == 12
    assert node.multiplier == 2.0
    assert node.loop is True

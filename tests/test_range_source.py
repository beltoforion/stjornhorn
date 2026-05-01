"""Unit tests for the RangeSource counter node."""
from __future__ import annotations

import pytest

from core.io_data import IoData, IoDataType
from core.port import InputPort
from nodes.sources.range_source import RangeSource


def _wire_capture(node: RangeSource) -> list[IoData]:
    captured: list[IoData] = []
    sink = InputPort("sink", {IoDataType.SCALAR})
    sink.add_listener(
        lambda: captured.append(sink.data) if sink.has_data else None
    )
    node.outputs[0].connect(sink)
    return captured


def test_tick_count_matches_emitted_frame_count() -> None:
    """tick_count() must agree with the actual number of frames emitted."""
    cases = [
        dict(min_value=0,   max_value=4,    increment=1.0),
        dict(min_value=1,   max_value=1000, increment=10.0),
        dict(min_value=0,   max_value=1,    increment=0.5),
    ]
    for params in cases:
        node = RangeSource()
        for k, v in params.items():
            setattr(node, k, v)
        captured = _wire_capture(node)
        node.before_run()
        node.process_impl()
        assert node.tick_count() == len(captured), f"mismatch for {params}"


def test_tick_count_empty_range() -> None:
    node = RangeSource()
    node.min_value = 10
    node.max_value = 5  # inverted → 0 ticks
    assert node.tick_count() == 0


def test_emits_scalar_iodata_per_frame() -> None:
    node = RangeSource()
    node.min_value = 0
    node.max_value = 4
    captured = _wire_capture(node)

    node.before_run()
    node.process_impl()

    assert len(captured) == 5
    assert all(d.type is IoDataType.SCALAR for d in captured)
    assert [int(d.payload.item()) for d in captured] == [0, 1, 2, 3, 4]


def test_default_range_is_zero_to_ninetynine() -> None:
    node = RangeSource()
    captured = _wire_capture(node)

    node.before_run()
    node.process_impl()

    assert len(captured) == 100
    assert int(captured[0].payload.item()) == 0
    assert int(captured[-1].payload.item()) == 99


def test_default_increment_is_one() -> None:
    """A brand-new node steps by 1, matching the pre-multiplier ``+1``
    counter behaviour."""
    node = RangeSource()
    assert node.increment == 1.0


def test_integer_increment_skips_values() -> None:
    node = RangeSource()
    node.min_value = 0
    node.max_value = 10
    node.increment = 2
    captured = _wire_capture(node)

    node.before_run()
    node.process_impl()

    assert [int(d.payload.item()) for d in captured] == [0, 2, 4, 6, 8, 10]


def test_integer_increment_emits_int() -> None:
    """A whole-number increment keeps the payload integer-valued so a
    Display label reads '42' rather than '42.0'."""
    node = RangeSource()
    node.min_value = 1
    node.max_value = 3
    node.increment = 1
    captured = _wire_capture(node)

    node.before_run()
    node.process_impl()

    for d in captured:
        # numpy 0-d int arrays expose .item() as a Python int.
        assert isinstance(d.payload.item(), int)


def test_fractional_increment_emits_float() -> None:
    node = RangeSource()
    node.min_value = 0
    node.max_value = 2
    node.increment = 0.5
    captured = _wire_capture(node)

    node.before_run()
    node.process_impl()

    values = [d.payload.item() for d in captured]
    assert values == [0.0, 0.5, 1.0, 1.5, 2.0]
    assert all(isinstance(v, float) for v in values)


def test_fractional_increment_handles_float_drift() -> None:
    """Floating-point drift (10 * 0.1 == 1.0000000000000002) must not
    truncate the last value — the iterator carries a small tolerance
    on the upper-bound check."""
    node = RangeSource()
    node.min_value = 0
    node.max_value = 1
    node.increment = 0.1
    captured = _wire_capture(node)

    node.before_run()
    node.process_impl()

    # 11 values: 0.0, 0.1, …, 1.0. Drift means the last one is
    # ~1.0000000000000002 rather than exactly 1.0 — accept either.
    assert len(captured) == 11
    assert abs(float(captured[-1].payload.item()) - 1.0) < 1e-9


def test_increment_setter_rejects_zero_and_negative() -> None:
    node = RangeSource()
    with pytest.raises(ValueError, match="increment must be > 0"):
        node.increment = 0
    with pytest.raises(ValueError, match="increment must be > 0"):
        node.increment = -0.5


def test_inverted_range_emits_nothing() -> None:
    """max_value < min_value is treated as an empty range — no values, no error."""
    node = RangeSource()
    node.min_value = 10
    node.max_value = 5
    captured = _wire_capture(node)

    node.before_run()
    node.process_impl()

    assert captured == []


def test_params_round_trip_through_setattr() -> None:
    """The setattr/getattr path used by widgets and flow-load must
    still work — verifies the property setters coerce types."""
    node = RangeSource()
    setattr(node, "min_value", "5")        # widget hands strings sometimes
    setattr(node, "max_value", 12.0)
    setattr(node, "increment", 2)

    assert node.min_value == 5
    assert node.max_value == 12
    assert node.increment == 2.0

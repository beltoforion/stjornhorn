"""Unit tests for the PlayGate debug node."""
from __future__ import annotations

from core.io_data import IoData, IoDataType
from core.port import InputPort, OutputPort
from nodes.debug.play_gate import PlayGate


def _wire(node: PlayGate) -> tuple[OutputPort, list[IoData]]:
    feeder = OutputPort("feeder", {IoDataType.SCALAR})
    feeder.connect(node.inputs[0])

    sink = InputPort("sink", {IoDataType.SCALAR})
    captured: list[IoData] = []

    # Fake-dispatcher: a real consumer node would clear() after
    # processing each fresh frame, so the next listener fire (e.g.
    # the one ``finish()`` triggers) doesn't double-count. The test
    # sink has no owning node, so clear here.
    def _on_change() -> None:
        if sink.is_fresh and sink.has_data:
            captured.append(sink.data)
            sink.clear()

    sink.add_listener(_on_change)
    node.outputs[0].connect(sink)
    return feeder, captured


def test_input_arrival_does_not_emit_until_play_clicked() -> None:
    """The whole point of the gate: data piles up until the user
    explicitly releases it."""
    node = PlayGate()
    feeder, captured = _wire(node)
    node.before_run()

    feeder.send(IoData.from_scalar(0))
    assert captured == []
    assert node.has_queued is True


def test_request_emit_releases_queued_frame() -> None:
    node = PlayGate()
    feeder, captured = _wire(node)
    node.before_run()

    feeder.send(IoData.from_scalar(7))
    node.request_emit()

    assert len(captured) == 1
    assert int(captured[0].payload) == 7
    assert node.has_queued is False


def test_request_emit_with_empty_queue_is_a_noop() -> None:
    """A double-click with nothing queued must not crash and must not
    re-emit a stale frame."""
    node = PlayGate()
    feeder, captured = _wire(node)
    node.before_run()

    feeder.send(IoData.from_scalar(1))
    node.request_emit()
    captured_count = len(captured)

    node.request_emit()  # second click on an empty queue

    assert len(captured) == captured_count


def test_inputs_queue_in_fifo_order() -> None:
    """FIFO: the user steps through the buffered frames in arrival
    order, one per click."""
    node = PlayGate()
    feeder, captured = _wire(node)
    node.before_run()

    feeder.send(IoData.from_scalar(1))
    feeder.send(IoData.from_scalar(2))
    feeder.send(IoData.from_scalar(3))

    assert node.queue_depth == 3

    node.request_emit()
    node.request_emit()
    node.request_emit()

    assert [int(d.payload) for d in captured] == [1, 2, 3]
    assert node.queue_depth == 0


def test_capacity_bound_drops_oldest_on_overflow() -> None:
    """When the queue is full, the oldest frame is evicted to make
    room for the newest — bounded memory on a runaway feeder."""
    node = PlayGate(capacity=3)
    feeder, captured = _wire(node)
    node.before_run()

    for i in range(5):
        feeder.send(IoData.from_scalar(i))

    assert node.queue_depth == 3

    while node.has_queued:
        node.request_emit()

    # The first two (0, 1) were evicted; we step through 2, 3, 4.
    assert [int(d.payload) for d in captured] == [2, 3, 4]


def test_capacity_must_be_positive() -> None:
    import pytest
    with pytest.raises(ValueError):
        PlayGate(capacity=0)


def test_state_callback_fires_on_queue_transitions() -> None:
    """The preview widget needs to know when the button should enable /
    disable. State changes are emitted only at empty↔non-empty
    transitions so a flurry of incoming frames doesn't spam the UI."""
    node = PlayGate()
    feeder, _ = _wire(node)
    node.before_run()

    states: list[bool] = []
    node.set_state_callback(lambda queued: states.append(queued))

    feeder.send(IoData.from_scalar(0))   # 0 -> 1: True
    feeder.send(IoData.from_scalar(1))   # 1 -> 2: no transition
    feeder.send(IoData.from_scalar(2))   # 2 -> 3: no transition
    node.request_emit()                  # 3 -> 2: no transition
    node.request_emit()                  # 2 -> 1: no transition
    node.request_emit()                  # 1 -> 0: False

    assert states == [True, False]


def test_before_run_clears_a_stale_queue() -> None:
    """A second run must not emit a frame left over from the first."""
    node = PlayGate()
    feeder, captured = _wire(node)
    node.before_run()

    feeder.send(IoData.from_scalar(99))
    assert node.has_queued is True

    node.before_run()
    assert node.has_queued is False
    node.request_emit()  # nothing to release
    assert captured == []


def test_upstream_finish_with_queue_defers_output_finish() -> None:
    """Regression: the upstream finishing while frames are queued
    must not close our output port — ``request_emit`` would otherwise
    raise "send() called after finish()" and the click would silently
    do nothing."""
    node = PlayGate()
    feeder, captured = _wire(node)
    node.before_run()

    feeder.send(IoData.from_scalar(7))
    feeder.send(IoData.from_scalar(8))
    feeder.send(IoData.from_scalar(9))
    feeder.finish()  # upstream done, three frames still queued

    assert node.outputs[0].finished is False, (
        "output must NOT finish while frames are still queued"
    )

    # Step through the three buffered frames; output must stay open
    # for the first two, finish only on the click that drains the
    # last one.
    node.request_emit()
    assert node.outputs[0].finished is False
    node.request_emit()
    assert node.outputs[0].finished is False
    node.request_emit()
    assert node.outputs[0].finished is True

    assert [int(d.payload) for d in captured] == [7, 8, 9]


def test_upstream_finish_with_empty_queue_propagates_immediately() -> None:
    """Symmetric to the deferred case: when nothing is queued, finish
    propagates the moment upstream signals end-of-stream so downstream
    sinks can wrap up promptly."""
    node = PlayGate()
    feeder, _ = _wire(node)
    node.before_run()

    feeder.finish()

    assert node.outputs[0].finished is True

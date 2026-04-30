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
    sink.add_listener(
        lambda: captured.append(sink.data) if sink.has_data else None
    )
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


def test_second_input_overwrites_first_when_play_not_pressed() -> None:
    """Latest-wins single-slot semantics: a second frame replaces the
    first, so the gate stays usable on fast streams without an
    unbounded queue."""
    node = PlayGate()
    feeder, captured = _wire(node)
    node.before_run()

    feeder.send(IoData.from_scalar(1))
    feeder.send(IoData.from_scalar(2))
    node.request_emit()

    assert len(captured) == 1
    assert int(captured[0].payload) == 2


def test_state_callback_fires_on_queue_transitions() -> None:
    """The preview widget needs to know when the button should enable /
    disable; the gate signals that through ``set_state_callback``."""
    node = PlayGate()
    feeder, _ = _wire(node)
    node.before_run()

    states: list[bool] = []
    node.set_state_callback(lambda queued: states.append(queued))

    feeder.send(IoData.from_scalar(0))
    node.request_emit()

    # before_run cleared the queue (False), then receive queued (True),
    # then request_emit released (False). The before_run notification
    # happens before the callback was attached, so it isn't observed.
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

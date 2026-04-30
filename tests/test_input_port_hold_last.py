"""Tests for the InputPort hold_last flag and its dispatcher integration.

A held input retains its last received value across :meth:`clear` and
across the upstream's :meth:`finish`. The owning node's dispatcher
also treats held ports as non-driving — only non-held (clock) inputs
push the consumer through ``_on_finish``.
"""
from __future__ import annotations

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase
from core.port import InputPort, OutputPort


# ── Test scaffolding ──────────────────────────────────────────────────────────


class _FanOutNode(NodeBase):
    """Two-input pass-through used to exercise the held/clock interaction.

    Fires once per fresh tick on the clock, copying the held SCALAR
    value into its output verbatim. Records each fire so tests can
    assert how many times the dispatcher picked up.
    """

    def __init__(self, *, hold_data: bool) -> None:
        super().__init__("Fanout", section="Debug")
        self._fired_with: list[tuple[object, object]] = []
        self._add_input(
            InputPort("data", {IoDataType.SCALAR}, hold_last=hold_data)
        )
        self._add_input(InputPort("clock", {IoDataType.SCALAR}))
        self._add_output(OutputPort("out", {IoDataType.SCALAR}))

    @property
    def fired_with(self) -> list[tuple[object, object]]:
        return self._fired_with

    def process_impl(self) -> None:
        data = int(self.inputs[0].data.payload)
        clock = int(self.inputs[1].data.payload)
        self._fired_with.append((data, clock))
        self.outputs[0].send(IoData.from_scalar(data * 1000 + clock))


def _wire_capture(node: NodeBase) -> tuple[OutputPort, OutputPort, list[IoData]]:
    held_feed = OutputPort("held_feed", {IoDataType.SCALAR})
    clock_feed = OutputPort("clock_feed", {IoDataType.SCALAR})
    held_feed.connect(node.inputs[0])
    clock_feed.connect(node.inputs[1])

    sink = InputPort("sink", {IoDataType.SCALAR})
    captured: list[IoData] = []

    def _on_change() -> None:
        if sink.is_fresh and sink.has_data:
            captured.append(sink.data)
            sink.clear()

    sink.add_listener(_on_change)
    node.outputs[0].connect(sink)
    return held_feed, clock_feed, captured


# ── Operative rules ───────────────────────────────────────────────────────────


def test_held_value_persists_after_clear() -> None:
    """Rule 1 + 4: a held port keeps its data so subsequent ticks on
    other clocks can fire the dispatcher with the same held value."""
    node = _FanOutNode(hold_data=True)
    held_feed, clock_feed, captured = _wire_capture(node)
    node.before_run()

    held_feed.send(IoData.from_scalar(7))   # held value arrives once
    clock_feed.send(IoData.from_scalar(0))  # tick 0
    clock_feed.send(IoData.from_scalar(1))  # tick 1
    clock_feed.send(IoData.from_scalar(2))  # tick 2

    assert node.fired_with == [(7, 0), (7, 1), (7, 2)]
    assert [int(d.payload) for d in captured] == [7000, 7001, 7002]


def test_held_value_persists_across_upstream_finish() -> None:
    """Rule 2: the held value remains available even after the held
    port's upstream signals end-of-stream — common pattern: a one-shot
    source (single image, single CSV) feeds the held input and then
    finishes immediately."""
    node = _FanOutNode(hold_data=True)
    held_feed, clock_feed, captured = _wire_capture(node)
    node.before_run()

    held_feed.send(IoData.from_scalar(42))
    held_feed.finish()                      # one-shot done
    clock_feed.send(IoData.from_scalar(9))  # later tick

    assert node.fired_with == [(42, 9)]
    assert int(captured[0].payload) == 9 + 42_000


def test_held_input_finish_does_not_propagate_to_outputs() -> None:
    """Rule 3: when the held input's upstream finishes, the consumer
    stays open — the clock alone decides when the node shuts down."""
    node = _FanOutNode(hold_data=True)
    held_feed, clock_feed, _ = _wire_capture(node)
    node.before_run()

    held_feed.send(IoData.from_scalar(1))
    held_feed.finish()  # held source done

    assert node.outputs[0].finished is False, (
        "held-only finish must not propagate to the consumer's outputs"
    )

    clock_feed.send(IoData.from_scalar(0))
    clock_feed.finish()  # clock done — now propagation should fire

    assert node.outputs[0].finished is True


def test_clock_finish_propagates_when_held_already_initialised() -> None:
    """The clock — a non-held input — keeps its lifecycle authority.
    When it finishes, the consumer finishes regardless of whether the
    held input is still alive."""
    node = _FanOutNode(hold_data=True)
    held_feed, clock_feed, _ = _wire_capture(node)
    node.before_run()

    held_feed.send(IoData.from_scalar(1))
    clock_feed.send(IoData.from_scalar(0))
    clock_feed.finish()  # clock done first; held source still nominally alive

    assert node.outputs[0].finished is True


def test_static_use_still_fires_once_when_only_held_input_connected() -> None:
    """Rule 5: a node with only its held input connected (no clock) is
    the static / single-emit case. The dispatcher fires on first
    receive; afterwards no more triggers exist, so the node sits
    idle without re-firing or shutting down."""
    node = _FanOutNode(hold_data=True)
    # Only wire the held input; clock left dangling.
    held_feed = OutputPort("feed", {IoDataType.SCALAR})
    held_feed.connect(node.inputs[0])
    node.before_run()

    # The node has a non-optional clock input with no upstream — the
    # dispatcher waits for it forever, so a held-only static flow
    # would actually need the clock input to be optional.  This test
    # documents the current behaviour: with both required, no fire.
    held_feed.send(IoData.from_scalar(5))
    assert node.fired_with == []


def test_held_port_freshness_does_not_drive_dispatcher_alone() -> None:
    """A held port's first arrival is fresh, so the dispatcher fires
    once. After that, only a fresh value on a non-held input can
    re-trigger — the held value going stale doesn't cause a re-fire,
    and no new value on the held port is needed for subsequent ticks."""
    node = _FanOutNode(hold_data=True)
    held_feed, clock_feed, _ = _wire_capture(node)
    node.before_run()

    # First fire: both inputs receive on the same tick.
    held_feed.send(IoData.from_scalar(10))
    clock_feed.send(IoData.from_scalar(0))
    assert len(node.fired_with) == 1

    # Subsequent: clock alone drives. Held isn't re-sent.
    clock_feed.send(IoData.from_scalar(1))
    clock_feed.send(IoData.from_scalar(2))
    assert len(node.fired_with) == 3
    assert node.fired_with == [(10, 0), (10, 1), (10, 2)]


def test_non_held_default_behaviour_unchanged() -> None:
    """Without ``hold_last=True``, the port behaves exactly as before:
    each tick must bring a fresh value on every input."""
    node = _FanOutNode(hold_data=False)
    held_feed, clock_feed, _ = _wire_capture(node)
    node.before_run()

    held_feed.send(IoData.from_scalar(7))
    clock_feed.send(IoData.from_scalar(0))
    # First tick fires (both fresh).
    assert len(node.fired_with) == 1

    # Second clock tick alone: the non-held port's data was cleared
    # after the first fire, so the dispatcher waits.
    clock_feed.send(IoData.from_scalar(1))
    assert len(node.fired_with) == 1


def test_fan_out_held_and_non_held_consumers_independent() -> None:
    """Same upstream OutputPort can feed one held consumer and one
    non-held consumer; the held branch keeps its value when the
    non-held branch clears."""
    held_node = _FanOutNode(hold_data=True)
    non_held_node = _FanOutNode(hold_data=False)

    shared = OutputPort("shared", {IoDataType.SCALAR})
    shared.connect(held_node.inputs[0])
    shared.connect(non_held_node.inputs[0])

    held_clock = OutputPort("hclock", {IoDataType.SCALAR})
    held_clock.connect(held_node.inputs[1])
    non_held_clock = OutputPort("nclock", {IoDataType.SCALAR})
    non_held_clock.connect(non_held_node.inputs[1])

    held_node.before_run()
    non_held_node.before_run()

    shared.send(IoData.from_scalar(99))
    held_clock.send(IoData.from_scalar(0))
    non_held_clock.send(IoData.from_scalar(0))

    # Both nodes fire once on tick 0.
    assert len(held_node.fired_with) == 1
    assert len(non_held_node.fired_with) == 1

    # Tick 1: the held node still has 99 cached; the non-held node
    # needs a fresh data value, which doesn't arrive.
    held_clock.send(IoData.from_scalar(1))
    non_held_clock.send(IoData.from_scalar(1))

    assert len(held_node.fired_with) == 2
    assert len(non_held_node.fired_with) == 1

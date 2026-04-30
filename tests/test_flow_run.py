"""Unit tests for :class:`core.flow.Flow.run` scheduling.

Covers the round-robin interleaving of streaming sources and the
stop-flag escape hatch the UI's Stop button drives.
"""
from __future__ import annotations

from typing import override

from core.flow import Flow
from core.io_data import IoData, IoDataType
from core.node_base import NodeBase, NodeParamType, SourceNodeBase
from core.port import InputPort, OutputPort


class _ScalarListSource(SourceNodeBase):
    """Streaming source that emits a fixed list of scalars, one per yield.

    Test fixture for round-robin scheduling — much simpler than spinning
    up a real RangeSource with min/max/increment semantics.
    """

    def __init__(self, name: str, values: list[int]) -> None:
        super().__init__(name, section="Sources")
        self._values = list(values)
        self._add_output(OutputPort("value", {IoDataType.SCALAR}))

    @override
    def iter_frames(self):
        for v in self._values:
            self.outputs[0].send(IoData.from_scalar(v))
            yield

    @override
    def process_impl(self) -> None:
        for _ in self.iter_frames():
            pass


class _PairCapture(NodeBase):
    """Two-input filter that records (a, b) on every dispatch fire.

    Lets a test assert exactly how the round-robin scheduler paired
    values from two streaming sources without going through an actual
    image pipeline. Both inputs are declared as param-style ports
    (``param_type`` in metadata) so they latch their last value
    across clear() — same shape as Overlay's xpos/ypos/angle ports.
    """

    def __init__(self) -> None:
        super().__init__("Pair Capture", section="Filters")
        self._add_input(InputPort(
            "a", {IoDataType.SCALAR},
            metadata={"param_type": NodeParamType.INT, "default": 0},
        ))
        self._add_input(InputPort(
            "b", {IoDataType.SCALAR},
            metadata={"param_type": NodeParamType.INT, "default": 0},
        ))
        self._add_output(OutputPort("out", {IoDataType.SCALAR}))
        self.captured: list[tuple[int, int]] = []

    @override
    def process_impl(self) -> None:
        a = int(self.inputs[0].data.payload.item())
        b = int(self.inputs[1].data.payload.item())
        self.captured.append((a, b))


def test_two_streaming_sources_interleave_frame_by_frame() -> None:
    """Two streaming SCALAR sources driving the same downstream node
    must each animate. Param-style ports latch their last value across
    clear(), so once both inputs have seen at least one value every
    subsequent send fires a dispatch — twice the frames of one source
    alone, with the two streams alternating one increment at a time.
    """
    src_a = _ScalarListSource("A", [0, 1, 2, 3, 4])
    src_b = _ScalarListSource("B", [100, 101, 102])
    pair = _PairCapture()

    flow = Flow("interleave")
    flow.add_node(src_a)
    flow.add_node(src_b)
    flow.add_node(pair)
    flow.connect(src_a, 0, pair, 0)
    flow.connect(src_b, 0, pair, 1)

    flow.run()

    # Round 1: A.send(0) — no dispatch (B has no data yet). B.send(100)
    # — dispatch (0, 100); both inputs latched. Round 2: A.send(1) —
    # dispatch (1, 100); B.send(101) — dispatch (1, 101). Round 3: A=2
    # then B=102 — dispatches (2, 101) and (2, 102). Round 4: A=3 — (3,
    # 102); B exhausts and finishes its output (input[1] retains 102).
    # Round 5: A=4 — (4, 102); A exhausts.
    assert pair.captured == [
        (0, 100),
        (1, 100),
        (1, 101),
        (2, 101),
        (2, 102),
        (3, 102),
        (4, 102),
    ]


def test_streaming_source_outlives_other_with_last_value_latched() -> None:
    """When the shorter source exhausts, its last value latches: the
    longer source keeps animating against the frozen value rather than
    the dispatcher silently stalling."""
    src_a = _ScalarListSource("A", [10, 20, 30, 40])
    src_b = _ScalarListSource("B", [99])  # one-frame source
    pair = _PairCapture()

    flow = Flow("outlive")
    flow.add_node(src_a)
    flow.add_node(src_b)
    flow.add_node(pair)
    flow.connect(src_a, 0, pair, 0)
    flow.connect(src_b, 0, pair, 1)

    flow.run()

    # Round 1: A=10, no dispatch. B=99, dispatch (10, 99). Round 2: A=20,
    # dispatch (20, 99); B exhausts. Round 3: A=30, dispatch (30, 99).
    # Round 4: A=40, dispatch (40, 99). Round 5: A exhausts.
    assert pair.captured == [(10, 99), (20, 99), (30, 99), (40, 99)]


def test_request_stop_unwinds_mid_run() -> None:
    """A Stop click between interleave steps must unwind cleanly: the
    in-flight step finishes, then no further dispatch fires. ``after_run``
    still runs on every node so file handles / video captures release."""
    src_a = _ScalarListSource("A", list(range(100)))
    src_b = _ScalarListSource("B", list(range(100)))
    pair = _PairCapture()

    flow = Flow("stoppable")
    flow.add_node(src_a)
    flow.add_node(src_b)
    flow.add_node(pair)
    flow.connect(src_a, 0, pair, 0)
    flow.connect(src_b, 0, pair, 1)

    # Wedge a stop request after the 5th captured pair by patching
    # the capture node's process_impl. Mirrors what the UI does on a
    # Stop click — flips the flag, and the Flow.run loop polls it
    # between every step.
    original_process = pair.process_impl

    def stop_after_five() -> None:
        original_process()
        if len(pair.captured) >= 5:
            flow.request_stop()

    pair.process_impl = stop_after_five  # type: ignore[method-assign]

    flow.run()

    # In-flight step finishes, then the loop unwinds. Allow some slack
    # — exactly when the stop flag is observed depends on iter ordering
    # within the round, so just assert "stopped well before the natural
    # end". Without the stop hook this would fire ~199 times (100+100-1).
    assert 5 <= len(pair.captured) < 100
    # First few frames mirror the deterministic round-robin alternation:
    # round 1 fires (0, 0); round 2 fires (1, 0) then (1, 1); round 3
    # fires (2, 1) then (2, 2). The exact prefix is stable.
    assert pair.captured[:5] == [(0, 0), (1, 0), (1, 1), (2, 1), (2, 2)]


def test_run_after_stop_starts_fresh() -> None:
    """A Run call after a Stop must start from scratch — the stop flag
    has to reset at the top of run(), otherwise the new run terminates
    before producing anything."""
    src = _ScalarListSource("A", [10, 20, 30])
    pair = _PairCapture()
    src_b = _ScalarListSource("B", [99])  # one-shot value, latches.

    flow = Flow("rerun")
    flow.add_node(src)
    flow.add_node(src_b)
    flow.add_node(pair)
    flow.connect(src, 0, pair, 0)
    flow.connect(src_b, 0, pair, 1)

    flow.request_stop()  # Stop set *before* run starts.
    # First run resets the flag at the top of run() and proceeds.
    flow.run()
    # B emits one value (99) which latches once it exhausts; A then runs
    # 10 → 20 → 30 against the latched B=99. Round 1: A=10, no dispatch
    # (B empty). B=99 → dispatch (10, 99); B exhausts. Round 2: A=20 →
    # (20, 99). Round 3: A=30 → (30, 99). Round 4: A exhausts.
    assert pair.captured == [(10, 99), (20, 99), (30, 99)]

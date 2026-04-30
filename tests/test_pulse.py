"""Tests for :class:`~nodes.filters.pulse.Pulse` and the SCALAR-port
auto-stamp convention it relies on.

The auto-stamp machinery lives in :meth:`OutputPort.send` — every
SCALAR input on the owning node lands in outgoing :class:`IoMeta`
under the port name. ``Pulse`` exists to make that convention
useful for the "fire one held image per clock tick" flow shape:
the held image rides the tick lifecycle, and the tick value lands
in meta as ``meta["tick"]`` so a downstream sink template can
reference ``$tick$`` without the sink needing a dedicated port.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from core.io_data import IoData, IoDataType, IoMeta
from core.node_base import NodeBase
from core.port import InputPort, OutputPort
from nodes.filters.pulse import Pulse
from nodes.sinks.file_sink import FileSink


def _make_image() -> np.ndarray:
    return np.full((4, 4, 3), 128, dtype=np.uint8)


# ── Pulse node mechanics ─────────────────────────────────────────────────────


def test_pulse_emits_held_data_once_per_tick() -> None:
    """One image in, one tick clock, N ticks → N emissions, all
    carrying the held image's payload."""
    pulse = Pulse()
    image_feeder = OutputPort("img", {IoDataType.IMAGE})
    tick_feeder  = OutputPort("tick", {IoDataType.SCALAR})
    image_feeder.connect(pulse.inputs[0])
    tick_feeder.connect(pulse.inputs[1])

    received: list[IoData] = []
    sink_in = InputPort("sink", {IoDataType.IMAGE})
    sink_in.add_listener(lambda: received.append(sink_in.data))
    pulse.outputs[0].connect(sink_in)

    pulse.before_run()
    image_feeder.send(IoData.from_image(_make_image()))
    image_feeder.finish()
    for i in range(1, 6):
        tick_feeder.send(IoData.from_scalar(i))

    assert len(received) == 5


def test_pulse_stamps_tick_value_into_outgoing_meta() -> None:
    """The auto-stamp convention writes the SCALAR ``tick`` port's
    current value into outgoing meta under the port name."""
    pulse = Pulse()
    image_feeder = OutputPort("img", {IoDataType.IMAGE})
    tick_feeder  = OutputPort("tick", {IoDataType.SCALAR})
    image_feeder.connect(pulse.inputs[0])
    tick_feeder.connect(pulse.inputs[1])

    received: list[IoData] = []
    sink_in = InputPort("sink", {IoDataType.IMAGE})
    sink_in.add_listener(lambda: received.append(sink_in.data))
    pulse.outputs[0].connect(sink_in)

    pulse.before_run()
    image_feeder.send(IoData.from_image(_make_image()))
    image_feeder.finish()
    for i in (3, 7, 11):
        tick_feeder.send(IoData.from_scalar(i))

    assert [d.meta["tick"] for d in received] == [3, 7, 11]


# ── End-to-end: Pulse → FileSink with $tick$ template ────────────────────────


def test_pulse_drives_filesink_via_tick_template(tmp_path: Path) -> None:
    """The canonical demo: ImageSource emits once, RangeSource
    ticks N times, Pulse rides the clock and stamps ``meta["tick"]``,
    FileSink writes one numbered file per tick."""
    pulse = Pulse()
    sink = FileSink()
    sink.output_path = tmp_path / "out_$tick:2$.png"

    image_feeder = OutputPort("img", {IoDataType.IMAGE})
    tick_feeder  = OutputPort("tick", {IoDataType.SCALAR})
    image_feeder.connect(pulse.inputs[0])
    tick_feeder.connect(pulse.inputs[1])
    pulse.outputs[0].connect(sink.inputs[0])

    pulse.before_run()
    sink.before_run()
    image_feeder.send(IoData.from_image(_make_image()))
    image_feeder.finish()
    for i in range(1, 11):
        tick_feeder.send(IoData.from_scalar(i))

    written = sorted(p.name for p in tmp_path.iterdir())
    assert written == [f"out_{i:02d}.png" for i in range(1, 11)]


# ── Auto-stamp convention itself ─────────────────────────────────────────────


class _TwoScalarFilter(NodeBase):
    """Test fixture: two SCALAR inputs, identity pass-through."""

    def __init__(self) -> None:
        super().__init__("Two Scalar", section="Test")
        self._add_input(InputPort("data", {IoDataType.IMAGE}))
        self._add_input(InputPort(
            "alpha", {IoDataType.SCALAR}, optional=True, default_value=0.5,
        ))
        self._add_input(InputPort(
            "beta",  {IoDataType.SCALAR}, optional=True, default_value=2,
        ))
        self._add_output(OutputPort("data", {IoDataType.IMAGE}))

    def process_impl(self) -> None:
        self.outputs[0].send(self.inputs[0].data)


def test_auto_stamp_writes_every_scalar_port() -> None:
    """A node with two SCALAR inputs stamps both into outgoing
    meta under their port names (no collision — distinct keys)."""
    node = _TwoScalarFilter()
    image_feeder = OutputPort("img", {IoDataType.IMAGE})
    alpha_feeder = OutputPort("a", {IoDataType.SCALAR})
    beta_feeder  = OutputPort("b", {IoDataType.SCALAR})
    image_feeder.connect(node.inputs[0])
    alpha_feeder.connect(node.inputs[1])
    beta_feeder.connect(node.inputs[2])

    received: list[IoData] = []
    sink_in = InputPort("sink", {IoDataType.IMAGE})
    sink_in.add_listener(lambda: received.append(sink_in.data))
    node.outputs[0].connect(sink_in)

    node.before_run()
    image_feeder.send(IoData.from_image(_make_image()))
    alpha_feeder.send(IoData.from_scalar(0.75))
    beta_feeder.send(IoData.from_scalar(7))

    last = received[-1]
    assert last.meta["alpha"] == 0.75
    assert last.meta["beta"] == 7


def test_auto_stamp_falls_back_to_default_for_unconnected_ports() -> None:
    """A SCALAR port with no upstream still stamps its inline default
    so a template that references the port doesn't silently
    disappear when someone unwires the clock."""
    node = _TwoScalarFilter()
    image_feeder = OutputPort("img", {IoDataType.IMAGE})
    image_feeder.connect(node.inputs[0])
    # alpha and beta intentionally not connected.

    received: list[IoData] = []
    sink_in = InputPort("sink", {IoDataType.IMAGE})
    sink_in.add_listener(lambda: received.append(sink_in.data))
    node.outputs[0].connect(sink_in)

    node.before_run()
    image_feeder.send(IoData.from_image(_make_image()))

    last = received[-1]
    assert last.meta["alpha"] == 0.5
    assert last.meta["beta"] == 2


def test_auto_stamp_skips_none_default() -> None:
    """A SCALAR port that has no upstream and no default value is
    not stamped — keeps meta clean for tokens the user never set."""

    class _NoDefault(NodeBase):
        def __init__(self) -> None:
            super().__init__("No Default", section="Test")
            self._add_input(InputPort("data", {IoDataType.IMAGE}))
            self._add_input(InputPort("gain", {IoDataType.SCALAR}, optional=True))
            self._add_output(OutputPort("data", {IoDataType.IMAGE}))

        def process_impl(self) -> None:
            self.outputs[0].send(self.inputs[0].data)

    node = _NoDefault()
    image_feeder = OutputPort("img", {IoDataType.IMAGE})
    image_feeder.connect(node.inputs[0])

    received: list[IoData] = []
    sink_in = InputPort("sink", {IoDataType.IMAGE})
    sink_in.add_listener(lambda: received.append(sink_in.data))
    node.outputs[0].connect(sink_in)

    node.before_run()
    image_feeder.send(IoData.from_image(_make_image()))

    assert "gain" not in received[-1].meta


def test_reserved_meta_key_rejected_at_port_declaration() -> None:
    """A node that tries to declare an input named ``frame_index``
    raises immediately — that name is owned by the framework's
    per-port emit counter and would silently clobber the stamp."""
    import pytest

    class _BadPortName(NodeBase):
        def __init__(self) -> None:
            super().__init__("Bad", section="Test")
            self._add_input(InputPort("frame_index", {IoDataType.SCALAR}))

        def process_impl(self) -> None:
            pass

    with pytest.raises(ValueError, match="frame_index"):
        _BadPortName()


def test_frame_index_stamp_survives_alongside_scalar_stamps() -> None:
    """``frame_index`` (framework-owned) and SCALAR-port stamps
    coexist in the same meta — one stamp call writes both."""
    node = _TwoScalarFilter()
    image_feeder = OutputPort("img", {IoDataType.IMAGE})
    alpha_feeder = OutputPort("a", {IoDataType.SCALAR})
    image_feeder.connect(node.inputs[0])
    alpha_feeder.connect(node.inputs[1])

    received: list[IoData] = []
    sink_in = InputPort("sink", {IoDataType.IMAGE})
    sink_in.add_listener(lambda: received.append(sink_in.data))
    node.outputs[0].connect(sink_in)

    node.before_run()
    for i in range(3):
        alpha_feeder.send(IoData.from_scalar(i / 10.0))
        image_feeder.send(IoData.from_image(_make_image()))

    # Each emission carries the per-output frame_index AND the
    # current alpha. Output port emit counter starts at 0 and
    # increments per send.
    indices = [d.meta["frame_index"] for d in received]
    alphas = [d.meta["alpha"] for d in received]
    assert indices == [0, 1, 2]
    assert alphas == [0.0, 0.1, 0.2]

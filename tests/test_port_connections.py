"""Unit tests for port connection semantics."""
from __future__ import annotations

import numpy as np
import pytest

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase
from core.port import InputPort, OutputPort


def _image_input(name: str = "in") -> InputPort:
    return InputPort(name, {IoDataType.IMAGE})


def _image_output(name: str = "out") -> OutputPort:
    return OutputPort(name, {IoDataType.IMAGE})


def test_output_can_fan_out_to_multiple_inputs() -> None:
    """One output may feed many inputs — fan-out is allowed."""
    out = _image_output()
    in1 = _image_input("in1")
    in2 = _image_input("in2")

    out.connect(in1)
    out.connect(in2)

    assert in1.upstream is out
    assert in2.upstream is out
    assert len(out.connections) == 2


def test_input_rejects_second_upstream() -> None:
    """An input already connected to one output cannot accept another."""
    out_a = _image_output("a")
    out_b = _image_output("b")
    target = _image_input()

    out_a.connect(target)
    with pytest.raises(TypeError, match="already connected"):
        out_b.connect(target)
    assert target.upstream is out_a
    assert target not in out_b.connections


def test_reconnecting_same_output_is_idempotent() -> None:
    """Connecting the same (output, input) pair twice is a no-op, not an error."""
    out = _image_output()
    target = _image_input()
    out.connect(target)
    out.connect(target)
    assert len(out.connections) == 1
    assert target.upstream is out


def test_disconnect_clears_upstream() -> None:
    out = _image_output()
    target = _image_input()
    out.connect(target)
    out.disconnect(target)
    assert target.upstream is None
    assert target not in out.connections


def test_disconnect_all_clears_every_upstream() -> None:
    out = _image_output()
    in1 = _image_input("in1")
    in2 = _image_input("in2")
    out.connect(in1)
    out.connect(in2)
    out.disconnect_all()
    assert in1.upstream is None
    assert in2.upstream is None
    assert out.connections == []


def test_input_reusable_after_disconnect() -> None:
    """After disconnecting, the input can accept a different output."""
    out_a = _image_output("a")
    out_b = _image_output("b")
    target = _image_input()

    out_a.connect(target)
    out_a.disconnect(target)
    out_b.connect(target)

    assert target.upstream is out_b


# ── Optional inputs ────────────────────────────────────────────────────────────

class _TwoInputNode(NodeBase):
    """Minimal NodeBase subclass with one required + one optional input,
    used to exercise the dispatcher behaviour around ``InputPort.optional``."""

    def __init__(self, optional: bool) -> None:
        super().__init__("two-input", section="Filters")
        self._add_input(InputPort("req", {IoDataType.IMAGE_GREY}))
        self._add_input(InputPort("opt", {IoDataType.IMAGE_GREY}, optional=optional))
        self._add_output(OutputPort("out", {IoDataType.IMAGE_GREY}))
        self.fired = 0
        self.saw_optional_data = False

    @property
    def params(self):  # type: ignore[override]
        return []

    def process_impl(self) -> None:  # type: ignore[override]
        self.fired += 1
        self.saw_optional_data = self.inputs[1].has_data
        self.outputs[0].send(self.inputs[0].data)


def _grey_io(value: int = 1) -> IoData:
    return IoData.from_greyscale(np.full((2, 2), value, dtype=np.uint8))


def test_optional_input_does_not_block_dispatch() -> None:
    """When an input is optional, the node fires once the required input
    arrives — even if the optional input never does."""
    node = _TwoInputNode(optional=True)
    node.inputs[0].receive(_grey_io())
    assert node.fired == 1
    assert node.saw_optional_data is False


def test_optional_input_is_consumed_when_present() -> None:
    """If the optional input is connected, the dispatcher waits for its
    frame before firing — an optional-but-wired input behaves like a
    required one, so producers emitting (B, G, R, A) as four sequential
    sends aren't raced by the node firing on just B/G/R."""
    node = _TwoInputNode(optional=True)
    up_opt = OutputPort("up_opt", {IoDataType.IMAGE_GREY})
    up_opt.connect(node.inputs[1])
    # Required input arrives first; optional is wired but silent.
    node.inputs[0].receive(_grey_io(3))
    assert node.fired == 0, "optional input is connected — must wait for its data"
    # Once the optional produces, the node fires with both payloads.
    up_opt.send(_grey_io(7))
    assert node.fired == 1
    assert node.saw_optional_data is True


def test_unconnected_optional_input_is_ignored() -> None:
    """Buffered data on an *unconnected* optional port must not block
    dispatch, but it's also not the intended usage. With no upstream,
    the port is simply skipped by the dispatcher."""
    node = _TwoInputNode(optional=True)
    node.inputs[0].receive(_grey_io(3))
    assert node.fired == 1
    assert node.saw_optional_data is False


def test_required_input_still_blocks_dispatch() -> None:
    """Without the optional flag, both inputs are required — pushing only
    one must not fire the node."""
    node = _TwoInputNode(optional=False)
    node.inputs[0].receive(_grey_io())
    assert node.fired == 0

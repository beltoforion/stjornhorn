"""Unit tests for port connection semantics."""
from __future__ import annotations

import pytest

from core.io_data import IoDataType
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

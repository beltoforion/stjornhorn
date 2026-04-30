"""Verify ``OutputPort.send`` stamps a per-port frame_index onto IoData.meta.

The stamping is the runner-side half of the metadata system: sources
populate ``source_path``; OutputPort populates ``frame_index`` so every
hop carries an unambiguous "current frame number" without producers
having to thread it manually.
"""
from __future__ import annotations

from core.io_data import IoData, IoDataType
from core.port import InputPort, OutputPort


def _wire_capture() -> tuple[OutputPort, list[IoData]]:
    out = OutputPort("out", {IoDataType.SCALAR})
    sink = InputPort("sink", {IoDataType.SCALAR})
    captured: list[IoData] = []
    sink.add_listener(
        lambda: captured.append(sink.data) if sink.has_data else None
    )
    out.connect(sink)
    return out, captured


def test_send_stamps_zero_based_frame_index_on_each_emit() -> None:
    out, captured = _wire_capture()

    for i in range(4):
        out.send(IoData.from_scalar(i))

    assert [d.meta["frame_index"] for d in captured] == [0, 1, 2, 3]


def test_send_overrides_caller_supplied_frame_index() -> None:
    """The producer's frame_index is overwritten on each hop so the
    receiver sees the upstream port's current count, not whatever the
    caller stamped earlier."""
    from core.io_data import IoMeta
    out, captured = _wire_capture()

    out.send(IoData.from_scalar(99, meta=IoMeta(frame_index=999)))

    assert captured[0].meta["frame_index"] == 0


def test_send_preserves_other_meta_keys() -> None:
    """Stamping frame_index must leave the other keys in the bag
    untouched so provenance reaches the sink."""
    from pathlib import Path

    from core.io_data import IoMeta

    out, captured = _wire_capture()
    meta = IoMeta(source_path=Path("ship.jpg"), timestamp=1700000000.0, custom_tag="abc")
    out.send(IoData.from_scalar(0, meta=meta))

    received = captured[0]
    assert received.meta["source_path"] == Path("ship.jpg")
    assert received.meta["timestamp"] == 1700000000.0
    assert received.meta["custom_tag"] == "abc"
    assert received.meta["frame_index"] == 0


def test_reset_rewinds_frame_counter() -> None:
    """``reset`` runs at the start of every flow run; the per-port
    counter must restart at 0 so two consecutive runs both stamp
    0,1,2,..."""
    out, captured = _wire_capture()

    out.send(IoData.from_scalar(0))
    out.send(IoData.from_scalar(1))
    out.reset()
    out.send(IoData.from_scalar(2))

    assert [d.meta["frame_index"] for d in captured] == [0, 1, 0]

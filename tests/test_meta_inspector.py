"""Unit tests for the MetaInspector debug node."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from core.io_data import IoData, IoDataType, IoMeta
from core.port import InputPort, OutputPort
from nodes.debug.meta_inspector import MetaInspector


def _wire(node: MetaInspector) -> tuple[OutputPort, InputPort, list[IoData]]:
    feeder = OutputPort("feeder", {IoDataType.SCALAR})
    feeder.connect(node.inputs[0])

    sink = InputPort("sink", {IoDataType.SCALAR})
    captured: list[IoData] = []
    sink.add_listener(
        lambda: captured.append(sink.data) if sink.has_data else None
    )
    node.outputs[0].connect(sink)
    return feeder, sink, captured


def test_passes_input_through_unchanged() -> None:
    node = MetaInspector()
    feeder, _, captured = _wire(node)
    node.before_run()

    feeder.send(IoData.from_scalar(42))

    assert len(captured) == 1
    assert int(captured[0].payload) == 42


def test_callback_receives_each_frame_with_meta() -> None:
    node = MetaInspector()
    feeder, _, _ = _wire(node)
    node.before_run()

    seen: list[IoData] = []
    node.set_frame_callback(lambda n: seen.append(n.last_inputs[0]))

    meta = IoMeta(source_path=Path("ship.jpg"))
    feeder.send(IoData.from_scalar(0, meta=meta))
    feeder.send(IoData.from_scalar(1, meta=meta))

    assert len(seen) == 2
    # source_path survives the per-port frame_index stamp.
    assert seen[0].meta["source_path"] == Path("ship.jpg")
    # frame_index reflects the upstream feeder's counter, not the
    # inspector's own outbound counter.
    assert [d.meta["frame_index"] for d in seen] == [0, 1]


def test_callback_is_optional() -> None:
    """A flow without a UI hook must still pass frames through."""
    node = MetaInspector()
    feeder, _, captured = _wire(node)
    node.before_run()

    feeder.send(IoData.from_scalar(0))
    feeder.send(IoData.from_scalar(1))

    assert len(captured) == 2

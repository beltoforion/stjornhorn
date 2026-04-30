"""Integration tests for FileSink filename templating.

Engine-level tests live in ``test_filename_template.py``. This file
exercises the wiring: FileSink reads ``IoMeta`` off its connected
inputs, merges them, and expands the ``output_path`` template per
write. Also covers the ``hold_last`` / ``tick`` clock interaction
that lets a one-shot image source drive multiple writes against a
streaming counter.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from core.io_data import IoData, IoDataType, IoMeta
from core.port import OutputPort
from nodes.sinks.file_sink import FileSink


def _make_image() -> np.ndarray:
    return np.full((4, 4, 3), 128, dtype=np.uint8)


# ── Legacy single-write path ──────────────────────────────────────────────────


def test_static_template_writes_one_file(tmp_path: Path) -> None:
    """No tokens → one file. Same behaviour as before this PR."""
    sink = FileSink()
    sink.output_path = tmp_path / "out.png"

    image_feeder = OutputPort("img", {IoDataType.IMAGE})
    image_feeder.connect(sink.inputs[0])

    sink.before_run()
    image_feeder.send(IoData.from_image(_make_image()))

    assert (tmp_path / "out.png").exists()


# ── Templated path with tick clock ────────────────────────────────────────────


def _wire_image_and_tick(sink: FileSink) -> tuple[OutputPort, OutputPort]:
    image_feeder = OutputPort("img", {IoDataType.IMAGE})
    tick_feeder = OutputPort("tick", {IoDataType.SCALAR})
    image_feeder.connect(sink.inputs[0])
    tick_feeder.connect(sink.inputs[1])
    return image_feeder, tick_feeder


def test_tick_drives_multiple_writes_with_held_image(tmp_path: Path) -> None:
    """Demo target: ImageSource emits ONCE, RangeSource ticks 10
    times, FileSink writes 10 numbered files. The image input is
    ``hold_last`` so it survives across ticks."""
    sink = FileSink()
    sink.output_path = tmp_path / "out_$frame_index:2$.png"

    image_feeder, tick_feeder = _wire_image_and_tick(sink)
    sink.before_run()

    # ImageSource-style: single emit, then finish (one-shot).
    image_feeder.send(IoData.from_image(_make_image()))
    image_feeder.finish()

    # RangeSource-style: ten ticks. The OutputPort.send stamps
    # frame_index 0..9 on each.
    for i in range(10):
        tick_feeder.send(IoData.from_scalar(i))

    written = sorted(p.name for p in tmp_path.iterdir())
    assert written == [f"out_{i:02d}.png" for i in range(10)]


def test_scalar_input_value_is_available_as_port_name_token(
    tmp_path: Path,
) -> None:
    """``$tick$`` resolves to the actual SCALAR value on the tick
    port, not the per-port emit counter — lets a
    ``RangeSource(1..10)`` template directly to ``out_01..out_10``."""
    sink = FileSink()
    sink.output_path = tmp_path / "out_$tick:2$.png"

    image_feeder, tick_feeder = _wire_image_and_tick(sink)
    sink.before_run()

    image_feeder.send(IoData.from_image(_make_image()))
    image_feeder.finish()

    for i in range(1, 11):
        tick_feeder.send(IoData.from_scalar(i))

    written = sorted(p.name for p in tmp_path.iterdir())
    assert written == [f"out_{i:02d}.png" for i in range(1, 11)]


def test_source_path_token_resolves_from_held_image(tmp_path: Path) -> None:
    """``$source_stem$`` flows through the held image's meta even
    while ``$frame_index$`` flows from the clock — the merge picks
    up source_path from image and frame_index from tick."""
    sink = FileSink()
    sink.output_path = tmp_path / "$source_stem$_$frame_index:1$.png"

    image_feeder, tick_feeder = _wire_image_and_tick(sink)
    sink.before_run()

    image_feeder.send(IoData.from_image(
        _make_image(), meta=IoMeta(source_path=Path("ship.jpg")),
    ))
    image_feeder.finish()

    tick_feeder.send(IoData.from_scalar(0))
    tick_feeder.send(IoData.from_scalar(1))

    written = sorted(p.name for p in tmp_path.iterdir())
    assert written == ["ship_0.png", "ship_1.png"]


def test_image_finish_alone_does_not_finish_sink_with_pending_clock(
    tmp_path: Path,
) -> None:
    """Lifecycle: held image's finish() is excluded from the dispatcher's
    "all inputs finished" decision (per Step 2). The sink keeps writing
    as the clock keeps ticking."""
    sink = FileSink()
    sink.output_path = tmp_path / "p_$frame_index$.png"

    image_feeder, tick_feeder = _wire_image_and_tick(sink)
    sink.before_run()

    image_feeder.send(IoData.from_image(_make_image()))
    image_feeder.finish()  # one-shot done
    tick_feeder.send(IoData.from_scalar(0))
    tick_feeder.send(IoData.from_scalar(1))

    assert {p.name for p in tmp_path.iterdir()} == {"p_0.png", "p_1.png"}


# ── Backwards compatibility ───────────────────────────────────────────────────


def test_legacy_flow_with_dangling_tick_still_works(tmp_path: Path) -> None:
    """Existing flows wire only the image input; the tick port is
    optional and dangling. The sink behaves exactly as before."""
    sink = FileSink()
    sink.output_path = tmp_path / "legacy.png"

    image_feeder = OutputPort("img", {IoDataType.IMAGE})
    image_feeder.connect(sink.inputs[0])

    sink.before_run()
    image_feeder.send(IoData.from_image(_make_image()))

    assert (tmp_path / "legacy.png").exists()

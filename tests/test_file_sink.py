"""Integration tests for FileSink filename templating.

Engine-level tests live in ``test_filename_template.py``. This file
exercises the wiring: FileSink reads ``IoMeta`` off its image input
and expands the ``output_path`` template per write. Multi-write
flows (``RangeSource → Pulse → FileSink``) are covered by
``test_pulse.py`` — FileSink itself only writes whatever arrives,
one frame in / one file out.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from core.io_data import IoData, IoDataType, IoMeta
from core.port import OutputPort
from nodes.sinks.file_sink import FileSink


def _make_image() -> np.ndarray:
    return np.full((4, 4, 3), 128, dtype=np.uint8)


# ── Single-write path ────────────────────────────────────────────────────────


def test_static_template_writes_one_file(tmp_path: Path) -> None:
    """No tokens → one file."""
    sink = FileSink()
    sink.output_path = tmp_path / "out.png"

    image_feeder = OutputPort("img", {IoDataType.IMAGE})
    image_feeder.connect(sink.inputs[0])

    sink.before_run()
    image_feeder.send(IoData.from_image(_make_image()))

    assert (tmp_path / "out.png").exists()


def test_frame_index_token_uses_per_port_emit_counter(tmp_path: Path) -> None:
    """``$frame_index$`` resolves to the per-port emit counter the
    framework stamps on every ``send`` (refactor M13 left this
    contract intact)."""
    sink = FileSink()
    sink.output_path = tmp_path / "f_$frame_index$.png"

    image_feeder = OutputPort("img", {IoDataType.IMAGE})
    image_feeder.connect(sink.inputs[0])
    sink.before_run()

    for _ in range(3):
        image_feeder.send(IoData.from_image(_make_image()))

    written = sorted(p.name for p in tmp_path.iterdir())
    assert written == ["f_0.png", "f_1.png", "f_2.png"]


def test_source_path_token_resolves_from_image_meta(tmp_path: Path) -> None:
    """``$source_stem$`` is derived from ``meta["source_path"]`` —
    the source node stamps the path; the sink reads it off the
    incoming image's meta."""
    sink = FileSink()
    sink.output_path = tmp_path / "$source_stem$.png"

    image_feeder = OutputPort("img", {IoDataType.IMAGE})
    image_feeder.connect(sink.inputs[0])
    sink.before_run()

    image_feeder.send(IoData.from_image(
        _make_image(), meta=IoMeta(source_path=Path("ship.jpg")),
    ))

    assert (tmp_path / "ship.png").exists()


def test_auto_stamped_scalar_token_resolves(tmp_path: Path) -> None:
    """A SCALAR-port value an upstream filter stamps into meta lands
    in the template as ``$<port_name>$`` — the M13 convention.

    Simulated here with a manually-stamped ``tick`` key in the
    IoMeta; the end-to-end test that exercises the auto-stamp
    machinery itself lives in ``test_pulse.py``."""
    sink = FileSink()
    sink.output_path = tmp_path / "out_$tick:2$.png"

    image_feeder = OutputPort("img", {IoDataType.IMAGE})
    image_feeder.connect(sink.inputs[0])
    sink.before_run()

    for i in range(1, 4):
        image_feeder.send(IoData.from_image(
            _make_image(), meta=IoMeta(tick=i),
        ))

    written = sorted(p.name for p in tmp_path.iterdir())
    assert written == ["out_01.png", "out_02.png", "out_03.png"]


def test_sink_has_no_tick_port(tmp_path: Path) -> None:
    """Regression guard: M13 dropped the explicit tick port. The
    sink takes one input only — the image. Cardinality control
    moves upstream (Pulse, or any filter with a SCALAR port)."""
    sink = FileSink()
    assert len(sink.inputs) == 1
    assert sink.inputs[0].name == "image"

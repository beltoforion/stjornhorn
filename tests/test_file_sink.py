"""Integration tests for FileSink filename templating.

Engine-level tests live in ``test_filename_template.py``. This file
exercises the wiring: FileSink reads ``IoMeta`` off its image input
and expands the ``output_path`` template per write. Multi-write
flows (``RangeSource → Repeat → FileSink``) are covered by
``test_repeat.py`` — FileSink itself only writes whatever arrives,
one frame in / one file out.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

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
    machinery itself lives in ``test_repeat.py``."""
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
    moves upstream (Repeat, or any filter with a SCALAR port)."""
    sink = FileSink()
    assert len(sink.inputs) == 1
    assert sink.inputs[0].name == "image"


# ── Non-ASCII paths + encode-failure handling ────────────────────────────────
#
# ``cv2.imwrite`` opens the destination through the C runtime's ANSI
# ``fopen`` on Windows, which silently fails on any path with characters
# outside the active code page — the ``ö`` in ``stjörnhorn`` was a
# real-world reproducer. The sink now encodes via ``cv2.imencode`` and
# streams the bytes through Python's ``open()`` (Path.write_bytes), so
# umlauts in the path are transparent. The tests below pin both the
# new success behaviour and the encode-failure error message.


def _drive_one_frame(sink: FileSink) -> None:
    image_feeder = OutputPort("img", {IoDataType.IMAGE})
    image_feeder.connect(sink.inputs[0])
    sink.before_run()
    image_feeder.send(IoData.from_image(_make_image()))


def test_writes_to_path_with_umlauts_succeeds(tmp_path: Path) -> None:
    """Headline regression: a parent folder with ``ö`` (the
    ``stjörnhorn`` case) must round-trip — the sink encodes in
    memory and writes the bytes via Python's file I/O, which on
    every supported OS handles non-ASCII paths."""
    sink = FileSink()
    out = tmp_path / "stjörnhorn" / "out.png"
    sink.output_path = out

    _drive_one_frame(sink)

    assert out.exists()
    # File must be a valid PNG, not an empty placeholder — i.e. the
    # encoded bytes actually landed on disk.
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_writes_to_path_with_multiple_non_ascii_chars(tmp_path: Path) -> None:
    """Multiple offenders in the path are not a problem — Python's
    open() handles arbitrary Unicode."""
    sink = FileSink()
    out = tmp_path / "öäü" / "café.png"
    sink.output_path = out

    _drive_one_frame(sink)

    assert out.exists() and out.stat().st_size > 0


def test_imencode_failure_raises_oserror_naming_the_extension(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the in-memory encoder rejects the format (typically an
    extension OpenCV doesn't ship a codec for), the user gets an
    explicit OSError pointing at the suffix rather than a silent
    write of an empty file."""
    monkeypatch.setattr(cv2, "imencode", lambda _ext, _img: (False, None))
    sink = FileSink()
    sink.output_path = tmp_path / "out.png"

    with pytest.raises(OSError) as exc_info:
        _drive_one_frame(sink)

    msg = str(exc_info.value)
    assert "failed to encode image" in msg
    assert "'.png'" in msg


def test_write_to_missing_directory_raises_oserror(tmp_path: Path) -> None:
    """Python's open() raises a clear OSError for filesystem-level
    failures; the sink doesn't swallow it. ``mkdir(parents=True)``
    handles missing intermediate dirs in the normal case, so we
    target a path whose *parent* is a regular file to force the
    failure."""
    blocker = tmp_path / "not_a_dir"
    blocker.write_bytes(b"x")
    sink = FileSink()
    sink.output_path = blocker / "out.png"

    with pytest.raises((OSError, NotADirectoryError, FileExistsError)):
        _drive_one_frame(sink)

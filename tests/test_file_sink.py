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


# ── Error handling: cv2.imwrite failure ──────────────────────────────────────
#
# ``cv2.imwrite`` returns False instead of raising when the underlying
# C-runtime ``fopen`` rejects the path. The sink's job is to translate
# that opaque False into an OSError whose message points at the most
# likely cause — non-ASCII characters in the path on Windows. The tests
# here monkeypatch ``cv2.imwrite`` to simulate the failure so they run
# the same way on every platform (Linux's GLIBC fopen accepts UTF-8).


def _drive_one_frame(sink: FileSink) -> None:
    image_feeder = OutputPort("img", {IoDataType.IMAGE})
    image_feeder.connect(sink.inputs[0])
    sink.before_run()
    image_feeder.send(IoData.from_image(_make_image()))


def test_imwrite_failure_on_ascii_path_raises_generic_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When cv2 refuses an ASCII path the message stays generic — we
    have no specific diagnosis, so the user gets the 'invalid for the
    current OS' fallback instead of a misleading umlaut hint."""
    monkeypatch.setattr(cv2, "imwrite", lambda _path, _img: False)
    sink = FileSink()
    sink.output_path = tmp_path / "out.png"

    with pytest.raises(OSError) as exc_info:
        _drive_one_frame(sink)

    msg = str(exc_info.value)
    assert "File Sink failed to write image" in msg
    assert "out.png" in msg
    assert "invalid" in msg.lower()
    assert "non-ASCII" not in msg
    assert "umlaut" not in msg.lower()


def test_imwrite_failure_on_umlaut_path_calls_out_offending_chars(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The headline regression: a path with ``ö`` (e.g. the user's
    home folder ``stjörnhorn``) must produce an error message that
    explicitly names the offending character and the encoding cause,
    so the user can act on it without consulting the source."""
    monkeypatch.setattr(cv2, "imwrite", lambda _path, _img: False)
    sink = FileSink()
    sink.output_path = tmp_path / "stjörnhorn" / "out.png"

    with pytest.raises(OSError) as exc_info:
        _drive_one_frame(sink)

    msg = str(exc_info.value)
    assert "File Sink failed to write image" in msg
    assert "non-ASCII" in msg
    assert "'ö'" in msg
    assert "umlaut" in msg.lower()
    assert "ANSI" in msg or "encoding" in msg.lower()


def test_imwrite_failure_message_lists_each_offender_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``ä`` and ``ö`` both present → both surface, each exactly once.
    Sorted order keeps the message deterministic across runs."""
    monkeypatch.setattr(cv2, "imwrite", lambda _path, _img: False)
    sink = FileSink()
    sink.output_path = tmp_path / "äöäö" / "out.png"

    with pytest.raises(OSError) as exc_info:
        _drive_one_frame(sink)

    msg = str(exc_info.value)
    assert msg.count("'ä'") == 1
    assert msg.count("'ö'") == 1


def test_imwrite_success_does_not_raise(tmp_path: Path) -> None:
    """Sanity counterpart to the failure tests: when cv2 actually
    writes the file, no error path triggers."""
    sink = FileSink()
    sink.output_path = tmp_path / "ok.png"
    _drive_one_frame(sink)
    assert (tmp_path / "ok.png").exists()

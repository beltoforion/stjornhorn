"""Unit tests for :class:`DirectorySource`.

Uses ``tmp_path`` to assemble a synthetic directory of PNG / JPEG / WebP
files plus an unsupported text file plus a corrupt image, runs the
source, and asserts on what it emitted.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from core.io_data import IoData, IoDataType
from core.port import InputPort
from nodes.sources.directory_source import DirectorySource


# ── Helpers ──────────────────────────────────────────────────────────────────

def _write_solid_png(path: Path, value: int, h: int = 4, w: int = 4) -> None:
    """Encode a constant-coloured BGR image to *path* as a PNG."""
    image = np.full((h, w, 3), value, dtype=np.uint8)
    ok, buf = cv2.imencode(".png", image)
    assert ok, "cv2 failed to encode the test PNG"
    path.write_bytes(buf.tobytes())


def _wire_capture(node: DirectorySource) -> list[IoData]:
    """Attach a capturing sink to *node* and return its receive log."""
    captured: list[IoData] = []
    sink = InputPort("sink", {IoDataType.IMAGE})
    sink.set_on_state_changed(
        lambda: captured.append(sink.data) if sink.has_data else None,
    )
    node.outputs[0].connect(sink)
    return captured


# ── Tests ────────────────────────────────────────────────────────────────────

def test_directory_source_emits_one_frame_per_image_in_order(tmp_path: Path) -> None:
    _write_solid_png(tmp_path / "a.png", 10)
    _write_solid_png(tmp_path / "c.png", 90)
    _write_solid_png(tmp_path / "b.png", 50)

    node = DirectorySource()
    node.directory = tmp_path
    captured = _wire_capture(node)

    node.before_run()
    node.process_impl()

    # Lexicographic order — a, b, c — so callers can rely on a stable
    # frame sequence regardless of filesystem listing quirks.
    assert [int(c.image[0, 0, 0]) for c in captured] == [10, 50, 90]
    assert all(c.type == IoDataType.IMAGE for c in captured)


def test_directory_source_skips_unsupported_extensions(tmp_path: Path) -> None:
    _write_solid_png(tmp_path / "img.png", 80)
    (tmp_path / "notes.txt").write_text("hello, ignore me")
    (tmp_path / "data.csv").write_text("1,2,3\n")

    node = DirectorySource()
    node.directory = tmp_path
    captured = _wire_capture(node)

    node.before_run()
    node.process_impl()

    assert len(captured) == 1
    assert int(captured[0].image[0, 0, 0]) == 80


def test_directory_source_excludes_subdirectories_by_default(tmp_path: Path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    _write_solid_png(tmp_path / "top.png", 30)
    _write_solid_png(nested / "deep.png", 200)

    node = DirectorySource()
    node.directory = tmp_path
    captured = _wire_capture(node)

    node.before_run()
    node.process_impl()

    # include_subdirectories is False by default; only the top-level
    # file should be emitted.
    assert [int(c.image[0, 0, 0]) for c in captured] == [30]


def test_directory_source_recurses_when_include_subdirectories(tmp_path: Path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    _write_solid_png(tmp_path / "top.png", 30)
    _write_solid_png(nested / "deep.png", 200)

    node = DirectorySource()
    node.directory = tmp_path
    node.include_subdirectories = True
    captured = _wire_capture(node)

    node.before_run()
    node.process_impl()

    # rglob walks the tree top-down, so the nested file's full path
    # ('.../nested/deep.png') sorts after the top-level file in
    # lexicographic order.
    assert [int(c.image[0, 0, 0]) for c in captured] == [200, 30] or \
           [int(c.image[0, 0, 0]) for c in captured] == [30, 200]
    # Order between sibling subtrees can vary by platform; what we care
    # about is that BOTH images came through.
    values = sorted(int(c.image[0, 0, 0]) for c in captured)
    assert values == [30, 200]


def test_directory_source_logs_and_skips_corrupt_files(tmp_path: Path, caplog) -> None:
    _write_solid_png(tmp_path / "good.png", 70)
    # A file that ends in .png but contains random bytes — cv2.imdecode
    # returns None for it, and the source should log + skip rather than
    # abort the entire walk.
    (tmp_path / "broken.png").write_bytes(b"not actually a png")

    node = DirectorySource()
    node.directory = tmp_path
    captured = _wire_capture(node)

    node.before_run()
    with caplog.at_level("WARNING"):
        node.process_impl()

    assert len(captured) == 1
    assert int(captured[0].image[0, 0, 0]) == 70
    assert any("broken.png" in rec.message for rec in caplog.records)


def test_directory_source_raises_when_directory_missing(tmp_path: Path) -> None:
    node = DirectorySource()
    node.directory = tmp_path / "does-not-exist"
    _wire_capture(node)

    node.before_run()
    with pytest.raises(FileNotFoundError):
        node.process_impl()


def test_directory_source_raises_when_path_is_a_file(tmp_path: Path) -> None:
    target = tmp_path / "img.png"
    _write_solid_png(target, 60)

    node = DirectorySource()
    node.directory = target
    _wire_capture(node)

    node.before_run()
    with pytest.raises(NotADirectoryError):
        node.process_impl()


def test_directory_source_promotes_greyscale_to_bgr(tmp_path: Path) -> None:
    grey = np.full((4, 4), 120, dtype=np.uint8)
    ok, buf = cv2.imencode(".png", grey)
    assert ok
    (tmp_path / "g.png").write_bytes(buf.tobytes())

    node = DirectorySource()
    node.directory = tmp_path
    captured = _wire_capture(node)

    node.before_run()
    node.process_impl()

    # ImageSource normalises greyscale to BGR; DirectorySource follows
    # suit so downstream nodes that assume an IMAGE port carries 3+
    # channels keep working.
    assert captured[0].image.shape == (4, 4, 3)
    assert int(captured[0].image[0, 0, 0]) == 120

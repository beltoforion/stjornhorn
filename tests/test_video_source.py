"""Unit tests for VideoSource — focused on the tick_count probe path
that the node header badge relies on.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from nodes.sources.video_source import VideoSource


def _write_mp4(path: Path, n_frames: int = 8, h: int = 32, w: int = 32) -> None:
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, 24.0, (w, h))
    try:
        for i in range(n_frames):
            frame = np.full((h, w, 3), i * 10, dtype=np.uint8)
            writer.write(frame)
    finally:
        writer.release()


def test_tick_count_reads_actual_frame_count(tmp_path: Path) -> None:
    video = tmp_path / "clip.mp4"
    _write_mp4(video, n_frames=12)

    node = VideoSource()
    node.file_path = video

    assert node.tick_count() == 12


def test_tick_count_caps_at_max_num_frames(tmp_path: Path) -> None:
    """When max_num_frames is set below the file's length, the badge
    reflects what the source will *actually* emit (the cap)."""
    video = tmp_path / "clip.mp4"
    _write_mp4(video, n_frames=20)

    node = VideoSource()
    node.file_path = video
    node.max_num_frames = 5

    assert node.tick_count() == 5


def test_tick_count_cap_above_video_length(tmp_path: Path) -> None:
    """Cap higher than the file's length: the actual frame count wins."""
    video = tmp_path / "clip.mp4"
    _write_mp4(video, n_frames=4)

    node = VideoSource()
    node.file_path = video
    node.max_num_frames = 100

    assert node.tick_count() == 4


def test_tick_count_returns_none_for_missing_file(tmp_path: Path) -> None:
    node = VideoSource()
    node.file_path = tmp_path / "does_not_exist.mp4"

    assert node.tick_count() is None


def test_tick_count_falls_back_to_max_when_file_unreadable(tmp_path: Path) -> None:
    """No file → fall back to max_num_frames if it's set; the badge
    still has something useful to show."""
    node = VideoSource()
    node.file_path = tmp_path / "missing.mp4"
    node.max_num_frames = 7

    assert node.tick_count() == 7


def test_tick_count_caches_by_path_and_mtime(tmp_path: Path, monkeypatch) -> None:
    """Second call with no file changes shouldn't re-open the video.

    The probe is metadata-only but still costs a syscall; tick_count is
    on the paint path, so it has to be cheap on repeat calls.
    """
    video = tmp_path / "clip.mp4"
    _write_mp4(video, n_frames=6)

    node = VideoSource()
    node.file_path = video

    open_count = 0
    real_capture = cv2.VideoCapture

    def counting_capture(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal open_count
        open_count += 1
        return real_capture(*args, **kwargs)

    monkeypatch.setattr(cv2, "VideoCapture", counting_capture)

    assert node.tick_count() == 6
    assert node.tick_count() == 6
    assert node.tick_count() == 6
    assert open_count == 1


def test_on_flow_loaded_warms_cache(tmp_path: Path, monkeypatch) -> None:
    """on_flow_loaded() should pre-probe so the first tick_count() call
    after load doesn't open the file (no UI stall on first paint)."""
    video = tmp_path / "clip.mp4"
    _write_mp4(video, n_frames=9)

    node = VideoSource()
    node.file_path = video
    node.on_flow_loaded()

    open_count = 0
    real_capture = cv2.VideoCapture

    def counting_capture(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal open_count
        open_count += 1
        return real_capture(*args, **kwargs)

    monkeypatch.setattr(cv2, "VideoCapture", counting_capture)

    assert node.tick_count() == 9
    assert open_count == 0  # cache was warmed; no file open in tick_count


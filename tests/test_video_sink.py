"""Unit tests for the VideoSink node."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from core.io_data import IoData, IoDataType
from core.port import OutputPort
from nodes.sinks.video_sink import VideoSink


def _wire(node: VideoSink, accepted_type: IoDataType = IoDataType.IMAGE) -> OutputPort:
    up = OutputPort("frames", {accepted_type})
    up.connect(node.inputs[0])
    return up


def _bgr_frame(value: int = 100, h: int = 32, w: int = 32) -> np.ndarray:
    return np.full((h, w, 3), value, dtype=np.uint8)


def test_video_sink_writes_playable_file_after_finish(tmp_path: Path) -> None:
    out = tmp_path / "out.mp4"
    node = VideoSink()
    node.output_path = out
    node.fps = 30.0

    up = _wire(node)
    node.before_run()
    for v in (10, 80, 160, 240):
        up.send(IoData.from_image(_bgr_frame(v)))
    up.finish()
    node.after_run(True)

    assert out.exists() and out.stat().st_size > 0

    cap = cv2.VideoCapture(str(out))
    try:
        # OpenCV's MP4V container reports 4 frames here. Don't be too
        # strict — some FourCC backends round; a positive count is the
        # real signal that the stream was finalised on finish().
        assert int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) >= 1
        assert int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) == 32
        assert int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) == 32
    finally:
        cap.release()


def test_video_sink_promotes_greyscale_to_bgr(tmp_path: Path) -> None:
    out = tmp_path / "grey.mp4"
    node = VideoSink()
    node.output_path = out

    up = _wire(node, IoDataType.IMAGE_GREY)
    node.before_run()
    for v in (40, 90, 140):
        up.send(IoData.from_greyscale(np.full((16, 24), v, dtype=np.uint8)))
    up.finish()
    node.after_run(True)

    assert out.exists() and out.stat().st_size > 0

    cap = cv2.VideoCapture(str(out))
    try:
        # Width/height ordering matches what we passed (24 wide, 16 tall).
        assert int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) == 24
        assert int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) == 16
    finally:
        cap.release()


def test_video_sink_rejects_shape_change_mid_stream(tmp_path: Path) -> None:
    node = VideoSink()
    node.output_path = tmp_path / "mismatch.mp4"

    up = _wire(node)
    node.before_run()
    up.send(IoData.from_image(_bgr_frame(value=50, h=16, w=16)))
    with pytest.raises(ValueError, match="frame shape changed"):
        up.send(IoData.from_image(_bgr_frame(value=80, h=24, w=24)))
    node.after_run(False)


def test_video_sink_rejects_non_positive_fps() -> None:
    node = VideoSink()
    with pytest.raises(ValueError):
        node.fps = 0


def test_video_sink_finish_releases_writer(tmp_path: Path) -> None:
    node = VideoSink()
    node.output_path = tmp_path / "release.mp4"

    up = _wire(node)
    node.before_run()
    up.send(IoData.from_image(_bgr_frame()))
    assert node._writer is not None  # opened on first frame

    up.finish()
    assert node._writer is None  # released by _on_finish
    node.after_run(True)

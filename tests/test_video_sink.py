"""Unit tests for the VideoSink node."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest
from typing_extensions import override

from core.flow import Flow
from core.io_data import IoData, IoDataType
from core.node_base import NodeParam, SourceNodeBase
from core.port import OutputPort
from nodes.filters.ncc import Ncc
from nodes.sinks.video_sink import VideoSink


class _FrameListSource(SourceNodeBase):
    """Minimal in-memory source — emits a preset list of BGR frames.

    Used by tests so we can drive the whole Flow without touching disk
    on the source side.
    """

    def __init__(self, frames: list[np.ndarray]) -> None:
        super().__init__("Frame List", section="Sources")
        self._frames = frames
        self._add_output(OutputPort("image", {IoDataType.IMAGE}))

    @property
    @override
    def params(self) -> list[NodeParam]:
        return []

    @override
    def process_impl(self) -> None:
        for frame in self._frames:
            self.outputs[0].send(IoData.from_image(frame))


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


class _GreyFrameListSource(SourceNodeBase):
    """Streaming greyscale source — emits every supplied frame in order."""

    def __init__(self, frames: list[np.ndarray]) -> None:
        super().__init__("Grey Frame List", section="Sources")
        self._frames = frames
        self._add_output(OutputPort("image", {IoDataType.IMAGE_GREY}))

    @property
    @override
    def params(self) -> list[NodeParam]:
        return []

    @override
    def process_impl(self) -> None:
        for frame in self._frames:
            self.outputs[0].send(IoData.from_greyscale(frame))


class _ReactiveImageSource(SourceNodeBase):
    """One-shot reactive greyscale source — emits a single frame."""

    def __init__(self, frame: np.ndarray) -> None:
        super().__init__("Reactive Image", section="Sources")
        self._frame = frame
        self._add_output(OutputPort("image", {IoDataType.IMAGE_GREY}))

    @property
    @override
    def params(self) -> list[NodeParam]:
        return []

    @property
    @override
    def is_reactive(self) -> bool:
        return True

    @override
    def process_impl(self) -> None:
        self.outputs[0].send(IoData.from_greyscale(self._frame))


def test_flow_latches_reactive_source_across_streaming_frames(tmp_path: Path) -> None:
    """A reactive (one-shot) source feeding one input of a multi-input
    filter must stay available while a streaming source drives the other
    input — otherwise only one paired frame would reach the sink.

    Regression for the debug_ncc_video flow: Ncc takes (image, template);
    with VideoSource on ``image`` and ImageSource on ``template``, every
    video frame must produce an Ncc output, not just the last one."""
    template = np.full((8, 8), 255, dtype=np.uint8)
    frames: list[np.ndarray] = []
    # Five frames, each with the bright patch in a different spot so the
    # matching peak differs per-frame — sanity check the flow actually
    # processes each one rather than re-emitting the same result.
    for i in range(5):
        f = np.zeros((32, 32), dtype=np.uint8)
        f[4 + i:10 + i, 4 + i:10 + i] = 255
        frames.append(f)

    image_src = _GreyFrameListSource(frames)
    template_src = _ReactiveImageSource(template)
    ncc = Ncc()
    sink = VideoSink()
    sink.output_path = tmp_path / "latched.mp4"
    sink.fps = 30.0

    flow = Flow("latched")
    # Registration order intentionally puts the streaming source first —
    # the runner must still schedule the reactive one-shot source ahead.
    flow.add_node(image_src)
    flow.add_node(template_src)
    flow.add_node(ncc)
    flow.add_node(sink)
    flow.connect(image_src, 0, ncc, 0)
    flow.connect(template_src, 0, ncc, 1)
    flow.connect(ncc, 0, sink, 0)

    flow.run()

    assert sink.output_path.exists() and sink.output_path.stat().st_size > 0
    cap = cv2.VideoCapture(str(sink.output_path))
    try:
        count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    finally:
        cap.release()
    # The pre-fix behaviour emitted exactly one frame; insist on more
    # than that. MP4V frame-count reporting can be fuzzy, so accept any
    # count comfortably above one.
    assert count >= len(frames) - 1, (
        f"expected ~{len(frames)} frames in output, got {count}"
    )


def test_flow_can_be_run_twice(tmp_path: Path) -> None:
    """Regression: running a flow a second time must not raise
    'send() called after finish()'. NodeBase.before_run resets every
    port's lifecycle state so stale ``finished`` flags from the
    previous run don't block the new one."""
    source = _FrameListSource([_bgr_frame(40), _bgr_frame(120), _bgr_frame(200)])
    sink = VideoSink()
    sink.output_path = tmp_path / "twice.mp4"

    flow = Flow("twice")
    flow.add_node(source)
    flow.add_node(sink)
    flow.connect(source, 0, sink, 0)

    flow.run()
    first_size = sink.output_path.stat().st_size

    flow.run()
    second_size = (tmp_path / "twice.mp4").stat().st_size

    assert first_size > 0
    assert second_size > 0

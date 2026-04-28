"""Sink-side placeholder expansion tests for ``FileSink`` / ``VideoSink``.

Drives each sink end-to-end (source → sink) so the test exercises both
``IoData.source_path`` propagation and the per-frame state on the sink.
Issue #159.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from typing_extensions import override

from core.flow import Flow
from core.io_data import IoData, IoDataType
from core.node_base import SourceNodeBase
from core.port import OutputPort
from nodes.sinks.file_sink import FileSink
from nodes.sinks.video_sink import VideoSink


class _PathStampedSource(SourceNodeBase):
    """Streams pre-built BGR frames, each tagged with a fixed source_path.

    Mirrors what ``ImageSource`` / ``VideoSource`` do — stamp each
    outgoing :class:`IoData` so downstream sinks can derive output
    filenames from the input.
    """

    def __init__(
        self,
        frames: list[np.ndarray],
        source_path: Path,
    ) -> None:
        super().__init__("Stamped Frames", section="Sources")
        self._frames = frames
        self._source_path = source_path
        self._add_output(OutputPort("image", {IoDataType.IMAGE}))

    @override
    def process_impl(self) -> None:
        for frame in self._frames:
            self.outputs[0].send(
                IoData.from_image(frame, source_path=self._source_path)
            )


def _bgr(value: int = 100, h: int = 16, w: int = 16) -> np.ndarray:
    return np.full((h, w, 3), value, dtype=np.uint8)


# ── FileSink ─────────────────────────────────────────────────────────────────

def test_file_sink_no_placeholders_writes_literal_path(tmp_path: Path) -> None:
    """Backwards-compat: a literal path with no tokens still writes the
    one configured file (last-write-wins on streams)."""
    sink = FileSink()
    sink.output_path = tmp_path / "out.png"

    src = _PathStampedSource([_bgr(40), _bgr(120)], source_path=Path("ship.jpg"))
    flow = Flow("literal")
    flow.add_node(src)
    flow.add_node(sink)
    flow.connect(src, 0, sink, 0)
    flow.run()

    assert (tmp_path / "out.png").exists()


def test_file_sink_input_stem_uses_source_filename(tmp_path: Path) -> None:
    sink = FileSink()
    sink.output_path = tmp_path / "$input_stem$.png"

    src = _PathStampedSource([_bgr(80)], source_path=Path("/in/ship.jpg"))
    flow = Flow("stem")
    flow.add_node(src)
    flow.add_node(sink)
    flow.connect(src, 0, sink, 0)
    flow.run()

    assert (tmp_path / "ship.png").exists()


def test_file_sink_frame_index_writes_one_file_per_frame(tmp_path: Path) -> None:
    """The big payoff of the feature: stream-to-stills without manual
    renaming. Three frames must land in three distinct files."""
    sink = FileSink()
    sink.output_path = tmp_path / "frame_$frame_index$.png"

    src = _PathStampedSource(
        [_bgr(40), _bgr(120), _bgr(200)], source_path=Path("clip.mp4"),
    )
    flow = Flow("frames")
    flow.add_node(src)
    flow.add_node(sink)
    flow.connect(src, 0, sink, 0)
    flow.run()

    files = sorted(tmp_path.glob("frame_*.png"))
    assert [f.name for f in files] == [
        "frame_0000.png", "frame_0001.png", "frame_0002.png",
    ]


def test_file_sink_flow_name_expands(tmp_path: Path) -> None:
    sink = FileSink()
    sink.output_path = tmp_path / "$input_stem$.$flow_name$.png"

    src = _PathStampedSource([_bgr(60)], source_path=Path("ship.jpg"))
    flow = Flow("denoise_v2")
    flow.add_node(src)
    flow.add_node(sink)
    flow.connect(src, 0, sink, 0)
    flow.run()

    assert (tmp_path / "ship.denoise_v2.png").exists()


def test_file_sink_frame_index_resets_between_runs(tmp_path: Path) -> None:
    """Running a flow twice must restart the frame counter — otherwise
    the second run would skip past the first run's filenames."""
    sink = FileSink()
    sink.output_path = tmp_path / "f_$frame_index$.png"

    src = _PathStampedSource([_bgr(40), _bgr(80)], source_path=Path("a.png"))
    flow = Flow("twice")
    flow.add_node(src)
    flow.add_node(sink)
    flow.connect(src, 0, sink, 0)

    flow.run()
    flow.run()

    # Both runs wrote to f_0000 and f_0001 — the second run overwrote
    # the files (correct: same input → same output) rather than rolling
    # the counter forward to f_0002 / f_0003.
    files = sorted(tmp_path.glob("f_*.png"))
    assert [f.name for f in files] == ["f_0000.png", "f_0001.png"]


# ── VideoSink ────────────────────────────────────────────────────────────────

def test_video_sink_input_stem_in_output_path(tmp_path: Path) -> None:
    sink = VideoSink()
    sink.output_path = tmp_path / "$input_stem$.mp4"
    sink.fps = 30.0

    src = _PathStampedSource(
        [_bgr(40), _bgr(120), _bgr(200)], source_path=Path("/in/clip.mp4"),
    )
    flow = Flow("video_stem")
    flow.add_node(src)
    flow.add_node(sink)
    flow.connect(src, 0, sink, 0)
    flow.run()

    out = tmp_path / "clip.mp4"
    assert out.exists() and out.stat().st_size > 0

    cap = cv2.VideoCapture(str(out))
    try:
        assert int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) >= 1
    finally:
        cap.release()


def test_video_sink_flow_name_expands(tmp_path: Path) -> None:
    sink = VideoSink()
    sink.output_path = tmp_path / "$input_stem$.$flow_name$.mp4"
    sink.fps = 30.0

    src = _PathStampedSource([_bgr(40), _bgr(120)], source_path=Path("clip.mp4"))
    flow = Flow("denoise_v2")
    flow.add_node(src)
    flow.add_node(sink)
    flow.connect(src, 0, sink, 0)
    flow.run()

    assert (tmp_path / "clip.denoise_v2.mp4").exists()

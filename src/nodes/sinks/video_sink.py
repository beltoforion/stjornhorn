from __future__ import annotations

from enum import IntEnum
from pathlib import Path

import cv2
import numpy as np
from typing_extensions import override

from constants import OUTPUT_DIR
from core.filename_template import expand as expand_template
from core.io_data import IMAGE_TYPES, IoData
from core.node_base import SinkNodeBase
from core.params import EnumParam, FilePathParam, FloatParam
from core.path_utils import resolve_against
from core.port import InputPort


class VideoCodec(IntEnum):
    """FourCC codec for the output video container.

    Values map directly to ``cv2.VideoWriter.fourcc`` codes; the integer
    representation persists cleanly in saved flows.
    """
    MP4V = 0
    XVID = 1


_CODEC_FOURCC: dict[VideoCodec, str] = {
    VideoCodec.MP4V: "mp4v",
    VideoCodec.XVID: "XVID",
}


class VideoSink(SinkNodeBase):
    """Sink node that encodes incoming frames to a video file.

    The encoder opens on the first frame and expects every later
    frame to match its shape and channel count. The file is finalised
    when the upstream stream ends.

    Paths inside :data:`OUTPUT_DIR` are stored relative to that folder
    so saved flows port cleanly across machines; anything outside is
    kept absolute.

    The ``output_path`` is a filename template resolved once when
    the encoder opens: ``$source_stem$``, ``$flow_name$`` and other
    meta-derived placeholders expand from the first frame's meta.
    Per-frame tokens
    like ``$frame_index$`` are not useful here — for per-frame paths
    use :class:`FileSink` instead.
    """

    output_path = FilePathParam(
        "out.mp4",
        constant=True,
        mode="save",
        filter="Video (*.mp4)",
        base_dir=OUTPUT_DIR,
        description=(
            "Where to encode the video. May contain $token$ placeholders "
            "expanded once at the moment the writer opens: "
            "$source_stem$, $source_name$, $source_ext$, $flow_name$. "
            "Per-frame tokens like $frame_index$ resolve against the "
            "first frame's meta; for per-frame paths use FileSink instead."
        ),
    )
    fps = FloatParam(30.0, min=0.0, min_exclusive=True, constant=True)
    codec = EnumParam(VideoCodec, VideoCodec.MP4V, constant=True)

    HEADER_ICON = "video_file"

    def __init__(self) -> None:
        super().__init__("Video Sink", section="Sinks")
        self._writer: cv2.VideoWriter | None = None
        self._frame_shape: tuple[int, ...] | None = None
        self._add_input(InputPort("image", set(IMAGE_TYPES)))
        self._apply_default_params()

    @override
    def _before_run_impl(self) -> None:
        super()._before_run_impl()
        # Defensive: if a previous run errored before _on_finish, the
        # writer may still be open. Reset state so this run starts clean.
        self._release_writer()
        self._frame_shape = None

    @override
    def process_impl(self) -> None:
        in_data: IoData = self.inputs[0].data
        frame: np.ndarray = in_data.image

        # Always encode as BGR so a single sink can consume either
        # colour or greyscale upstream pipelines without producing
        # codec-unfriendly monochrome video.
        if frame.ndim == 2:
            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)

        if self._writer is None:
            # Resolve the filename template against the first frame's
            # meta — fixed for the life of the writer.
            self._open_writer(frame, in_data)
            self._frame_shape = frame.shape
        elif frame.shape != self._frame_shape:
            raise ValueError(
                f"VideoSink frame shape changed mid-stream: "
                f"first={self._frame_shape}, now={frame.shape}"
            )

        self._writer.write(frame)

    @override
    def _on_finish(self) -> None:
        self._release_writer()

    @override
    def _after_run_impl(self, run_success: bool) -> None:
        super()._after_run_impl(run_success)
        # Belt-and-braces: if the run aborted before finish() propagated,
        # close the writer here so the partial file is flushed and the
        # OS handle isn't leaked across runs.
        self._release_writer()

    # ── Internals ──────────────────────────────────────────────────────────────

    def _resolved_path(self, in_data: IoData | None = None) -> Path:
        meta = dict(in_data.meta) if in_data is not None else {}
        # ``output_path`` is a Path after the descriptor coerces it; the
        # engine works on strings so we round-trip via ``str``.
        rendered = expand_template(str(self._output_path), meta)
        return resolve_against(Path(rendered), OUTPUT_DIR)

    def _open_writer(self, frame: np.ndarray, in_data: IoData) -> None:
        h, w = frame.shape[:2]
        fourcc = cv2.VideoWriter.fourcc(*_CODEC_FOURCC[self._codec])
        path = self._resolved_path(in_data)
        path.parent.mkdir(parents=True, exist_ok=True)
        # frame is BGR by the time this is called, so isColor=True always.
        self._writer = cv2.VideoWriter(
            str(path), fourcc, self._fps, (w, h), isColor=True,
        )
        if not self._writer.isOpened():
            self._writer = None
            raise OSError(f"cv2.VideoWriter failed to open: {path}")

    def _release_writer(self) -> None:
        if self._writer is not None:
            self._writer.release()
            self._writer = None

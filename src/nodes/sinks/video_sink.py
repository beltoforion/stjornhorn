from __future__ import annotations

from enum import IntEnum
from pathlib import Path

import cv2
import numpy as np
from typing_extensions import override

from constants import OUTPUT_DIR
from core.io_data import IMAGE_TYPES
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

    Wraps :class:`cv2.VideoWriter`. The writer is initialised lazily on
    the first frame so its dimensions and channel count can be inferred
    from the data — every subsequent frame must match. The writer is
    released on :meth:`_on_finish`, triggered by the runner's
    end-of-stream signal, which is what turns the in-progress file into
    a playable container.

    Paths inside :data:`OUTPUT_DIR` are stored relative to that folder
    so saved flows port cleanly across machines; anything outside is
    kept absolute. Ported from the original OCVL ``VideoSink`` — the
    interactive preview, monitor-relative resize and blocking
    ``waitKey`` are dropped, and GIF support is omitted because
    ``imageio`` isn't a pipeline dependency.
    """

    output_path = FilePathParam(
        "out.mp4",
        constant=True,
        mode="save",
        filter="Video (*.mp4)",
        base_dir=OUTPUT_DIR,
    )
    fps = FloatParam(30.0, min=0.0, min_exclusive=True, constant=True)
    codec = EnumParam(VideoCodec, VideoCodec.MP4V, constant=True)

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
        frame: np.ndarray = self.inputs[0].data.image

        # Always encode as BGR so a single sink can consume either
        # colour or greyscale upstream pipelines without producing
        # codec-unfriendly monochrome video.
        if frame.ndim == 2:
            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)

        if self._writer is None:
            self._open_writer(frame)
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

    def _resolved_path(self) -> Path:
        return resolve_against(self._output_path, OUTPUT_DIR)

    def _open_writer(self, frame: np.ndarray) -> None:
        h, w = frame.shape[:2]
        fourcc = cv2.VideoWriter.fourcc(*_CODEC_FOURCC[self._codec])
        path = self._resolved_path()
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

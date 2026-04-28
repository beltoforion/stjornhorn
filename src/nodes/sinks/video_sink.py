from __future__ import annotations

from datetime import datetime
from enum import IntEnum
from pathlib import Path

import cv2
import numpy as np
from typing_extensions import override

from constants import OUTPUT_DIR
from core.io_data import IMAGE_TYPES
from core.node_base import (
    NodeParam,
    NodeParamType,
    SinkNodeBase,
    get_current_flow_name,
)
from core.path_placeholders import expand_placeholders, has_placeholders
from core.path_utils import resolve_against, store_relative_to
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

    def __init__(self) -> None:
        super().__init__("Video Sink", section="Sinks")

        self._output_path: Path = Path("out.mp4")
        self._fps: float = 30.0
        self._codec: VideoCodec = VideoCodec.MP4V

        self._writer: cv2.VideoWriter | None = None
        self._frame_shape: tuple[int, ...] | None = None

        # Per-run state for placeholder expansion. ``$frame_index$`` on a
        # video sink locks to ``0000`` (one container, one starting frame)
        # — the index is per-file, not per-frame inside the file.
        self._run_started_at: datetime | None = None

        self._add_input(InputPort("image", set(IMAGE_TYPES)))
        self._add_param(NodeParam(
            "output_path",
            NodeParamType.FILE_PATH,
            default="out.mp4",
            metadata={
                "mode": "save",
                "filter": "Video (*.mp4)",
                "base_dir": OUTPUT_DIR,
                "description": (
                    "Where to write the encoded video. Accepts $token$ "
                    "placeholders resolved on writer open — e.g. "
                    "$input_stem$ (source filename), $flow_name$, "
                    "$timestamp$. The path is fixed for the whole stream, "
                    "so placeholders that change per frame "
                    "($frame_index$) are not useful here."
                ),
            },
        ))
        self._add_param(NodeParam(
            "fps",
            NodeParamType.FLOAT,
            default=30.0,
        ))
        self._add_param(NodeParam(
            "codec",
            NodeParamType.ENUM,
            default=VideoCodec.MP4V,
            metadata={"enum": VideoCodec},
        ))
        self._apply_default_params()

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def output_path(self) -> Path:
        return self._output_path

    @output_path.setter
    def output_path(self, output_path: str | Path) -> None:
        self._output_path = store_relative_to(output_path, OUTPUT_DIR)

    @property
    def fps(self) -> float:
        return self._fps

    @fps.setter
    def fps(self, value: float) -> None:
        v = float(value)
        if v <= 0:
            raise ValueError(f"fps must be > 0 (got {v})")
        self._fps = v

    @property
    def codec(self) -> VideoCodec:
        return self._codec

    @codec.setter
    def codec(self, value: int | VideoCodec) -> None:
        try:
            self._codec = VideoCodec(value)
        except ValueError as e:
            raise ValueError(
                f"codec must be one of {[c.value for c in VideoCodec]} (got {value!r})"
            ) from e

    # ── SinkNodeBase interface ──────────────────────────────────────────────────

    @override
    def _before_run_impl(self) -> None:
        super()._before_run_impl()
        # Defensive: if a previous run errored before _on_finish, the
        # writer may still be open. Reset state so this run starts clean.
        self._release_writer()
        self._frame_shape = None
        self._run_started_at = datetime.now()

    @override
    def process_impl(self) -> None:
        in_data = self.inputs[0].data
        frame: np.ndarray = in_data.image

        # Always encode as BGR so a single sink can consume either
        # colour or greyscale upstream pipelines without producing
        # codec-unfriendly monochrome video.
        if frame.ndim == 2:
            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)

        if self._writer is None:
            self._open_writer(frame, source_path=in_data.source_path)
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

    def _resolved_path(self, source_path: Path | None = None) -> Path:
        """Return an absolute path; expands ``$token$`` placeholders. Issue: #159."""
        raw = str(self._output_path)
        if has_placeholders(raw):
            expanded = expand_placeholders(
                raw,
                source_path=source_path,
                flow_name=get_current_flow_name(),
                # VideoSink writes one file per run, so frame_index is
                # always the start-of-stream value.
                frame_index=0,
                run_started_at=self._run_started_at,
            )
            return resolve_against(Path(expanded), OUTPUT_DIR)
        return resolve_against(self._output_path, OUTPUT_DIR)

    def _open_writer(self, frame: np.ndarray, source_path: Path | None = None) -> None:
        h, w = frame.shape[:2]
        fourcc = cv2.VideoWriter.fourcc(*_CODEC_FOURCC[self._codec])
        path = self._resolved_path(source_path=source_path)
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

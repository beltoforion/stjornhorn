from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import cv2
from typing_extensions import override

from constants import INPUT_DIR
from core.io_data import IoData, IoDataType
from core.node_base import SourceNodeBase
from core.params import FilePathParam, IntParam
from core.path_utils import resolve_against
from core.port import OutputPort

_SUPPORTED_EXTS = {".mp4", ".avi", ".mov", ".mkv"}


class VideoSource(SourceNodeBase):
    """Source node that reads video frames from a file.

    Supported formats: MP4, AVI, MOV, MKV. Paths inside
    :data:`INPUT_DIR` are stored relative to that folder so saved
    flows port cleanly. Not reactive — runs only on Run, to avoid
    restarting long decodes on every keystroke.
    """

    file_path = FilePathParam(
        "video.mp4",
        constant=True,
        filter="Video (*.mp4 *.avi *.mov *.mkv)",
        base_dir=INPUT_DIR,
    )
    max_num_frames = IntParam(-1, constant=True)

    HEADER_ICON = "movie"

    def __init__(self) -> None:
        super().__init__("Video Source", section="Sources")
        self._add_output(OutputPort("image", {IoDataType.IMAGE}))
        self._apply_default_params()
        # Probed total frame count, cached by (path, mtime). Populated
        # eagerly by on_flow_loaded() and lazily by tick_count() if the
        # node was added in the editor rather than restored from a file.
        self._frame_count_cache: tuple[tuple[str, float], int] | None = None

    @override
    def on_flow_loaded(self) -> None:
        # Warm the frame-count cache at flow-load time so the first
        # repaint doesn't stall on cv2.VideoCapture.
        self._probe_frame_count()

    @override
    def tick_count(self) -> int | None:
        total = self._probe_frame_count()
        capped = self._max_num_frames if self._max_num_frames >= 0 else None
        if total is None:
            return capped
        if capped is None:
            return total
        return min(total, capped)

    @override
    def iter_frames(self) -> Iterator[None]:
        """Per-frame generator: one ``yield`` per decoded video frame.

        The ``finally`` releases the OpenCV capture even if the flow
        runner aborts mid-stream (Stop button) — the generator's
        ``close()`` triggers it via ``GeneratorExit``.
        """
        resolved = self._resolved_path()
        if not resolved.exists():
            raise FileNotFoundError(f"Input file not found: {resolved}")

        ext = resolved.suffix.lower()
        if ext not in _SUPPORTED_EXTS:
            raise ValueError(
                f"Unsupported file type '{ext}'. "
                f"Supported: {_SUPPORTED_EXTS}"
            )

        cap = cv2.VideoCapture(str(resolved))
        try:
            frame_count = 0
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                self.outputs[0].send(IoData.from_image(frame))
                frame_count += 1
                yield
                if self._max_num_frames >= 0 and frame_count >= self._max_num_frames:
                    break
        finally:
            cap.release()

    @override
    def process_impl(self) -> None:
        """Direct-invocation path: drain :meth:`iter_frames` in one call."""
        for _ in self.iter_frames():
            pass

    # ── Internals ──────────────────────────────────────────────────────────────

    def _resolved_path(self) -> Path:
        """Return an absolute path; relative values are joined with INPUT_DIR."""
        return resolve_against(self._file_path, INPUT_DIR)

    def _probe_frame_count(self) -> int | None:
        """Return the total frame count of the configured video file.

        Reads ``cv2.CAP_PROP_FRAME_COUNT`` (metadata only, no decode) and
        caches the result keyed by ``(path, mtime)`` so a repaint loop
        doesn't re-open the file. Returns ``None`` when the path is
        empty / missing / unreadable so the header badge silently
        disappears rather than showing a misleading number.
        """
        try:
            path = self._resolved_path()
        except (TypeError, ValueError):
            return None
        if not path.is_file() or path.suffix.lower() not in _SUPPORTED_EXTS:
            return None
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return None
        cache_key = (str(path), mtime)
        if self._frame_count_cache is not None and self._frame_count_cache[0] == cache_key:
            return self._frame_count_cache[1]
        cap = cv2.VideoCapture(str(path))
        try:
            if not cap.isOpened():
                return None
            count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        finally:
            cap.release()
        if count <= 0:
            return None
        self._frame_count_cache = (cache_key, count)
        return count

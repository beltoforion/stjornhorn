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

    Supported formats: MP4, AVI, MOV, MKV.

    Paths inside the application's :data:`INPUT_DIR` are stored — and
    therefore displayed — relative to that folder. Anything outside is
    kept as an absolute path. Relative paths are resolved against
    ``INPUT_DIR`` at run time, which keeps saved flows portable across
    machines that share the same input layout.

    Unlike :class:`ImageSource`, this source is **not** reactive — the flow
    only runs when the Run button is pressed.  This avoids restarting a
    potentially long video decode on every keystroke.

    Parameters:
      file_path      -- path to the input video (relative to INPUT_DIR when possible)
      max_num_frames -- maximum number of frames to decode (-1 = all)
    """

    file_path = FilePathParam(
        "video.mp4",
        constant=True,
        filter="Video (*.mp4 *.avi *.mov *.mkv)",
        base_dir=INPUT_DIR,
    )
    max_num_frames = IntParam(-1, constant=True)

    def __init__(self) -> None:
        super().__init__("Video Source", section="Sources")
        self._add_output(OutputPort("image", {IoDataType.IMAGE}))
        self._apply_default_params()

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

from __future__ import annotations

from pathlib import Path

import cv2
from typing_extensions import override

from constants import INPUT_DIR
from core.io_data import IoData, IoDataType
from core.node_base import SourceNodeBase, NodeParam, NodeParamType
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

    def __init__(self) -> None:
        super().__init__("Video Source", section="Sources")
        self._file_path: Path = Path()
        self._max_num_frames: int = -1
        self._add_output(OutputPort("image", {IoDataType.IMAGE}))
        self._apply_default_params()

    # ── Parameters ─────────────────────────────────────────────────────────────

    @property
    @override
    def params(self) -> list[NodeParam]:
        return [
            NodeParam(
                "file_path",
                NodeParamType.FILE_PATH,
                {
                    "default": "video.mp4",
                    "filter": "Video (*.mp4 *.avi *.mov *.mkv)",
                    "base_dir": INPUT_DIR,
                },
            ),
            NodeParam("max_num_frames", NodeParamType.INT, {"default": -1}),
        ]

    @property
    def file_path(self) -> Path:
        return self._file_path

    @file_path.setter
    def file_path(self, path: str | Path) -> None:
        p = Path(path)
        if p.is_absolute():
            try:
                p = p.resolve().relative_to(INPUT_DIR.resolve())
            except (OSError, ValueError):
                pass  # outside INPUT_DIR — keep absolute
        self._file_path = p

    @property
    def max_num_frames(self) -> int:
        return self._max_num_frames

    @max_num_frames.setter
    def max_num_frames(self, value: int) -> None:
        self._max_num_frames = int(value)

    # ── SourceNodeBase interface ────────────────────────────────────────────────

    @override
    def process_impl(self) -> None:
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
                if self._max_num_frames >= 0 and frame_count >= self._max_num_frames:
                    break
        finally:
            cap.release()

    # ── Internals ──────────────────────────────────────────────────────────────

    def _resolved_path(self) -> Path:
        """Return an absolute path; relative values are joined with INPUT_DIR."""
        if self._file_path.is_absolute():
            return self._file_path
        return INPUT_DIR / self._file_path

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import rawpy
from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import SourceNodeBase, NodeParam, NodeParamType
from core.port import OutputPort

_SUPPORTED_IMAGE_EXTS = {".jpg", ".jpeg", ".png"}
_SUPPORTED_VIDEO_EXTS = {".mp4"}
_SUPPORTED_RAW_EXTS   = {".cr2"}


class FileSource(SourceNodeBase):
    """Source node that reads images or video frames from a file.

    Supported formats:
      - Images: JPEG, PNG
      - Video:  MP4 (sends one frame per IoData, then EndOfStream)
      - RAW:    CR2 (requires rawpy)

    Parameters:
      file_path      -- path to the input file
      max_num_frames -- maximum number of video frames to read (-1 = all)
    """

    def __init__(self) -> None:
        super().__init__("File Source")
        self._file_path: Path = Path()
        self._max_num_frames: int = -1
        self._add_output(OutputPort("image", {IoDataType.IMAGE}))
        # Push the declared NodeParam defaults onto the instance so the
        # node's state matches what its params metadata promises (and
        # what the UI displays) from the moment it is constructed.
        self._apply_default_params()

    # ── Parameters ─────────────────────────────────────────────────────────────

    @property
    @override
    def params(self) -> list[NodeParam]:
        return [
            NodeParam("file_path",      NodeParamType.FILE_PATH, {"default": "./input/example.jpg"}),
            NodeParam("max_num_frames", NodeParamType.INT,       {"default": -1}),
        ]

    @property
    def file_path(self) -> Path:
        return self._file_path

    @file_path.setter
    def file_path(self, path: str | Path) -> None:
        p = Path(path)
        self._file_path = p
        if p.name and not p.exists():
            self.set_error(f"File not found: {p}")
        else:
            self.clear_error()

    @property
    def max_num_frames(self) -> int:
        return self._max_num_frames

    @max_num_frames.setter
    def max_num_frames(self, value: int) -> None:
        self._max_num_frames = value

    # ── SourceNodeBase interface ────────────────────────────────────────────────

    @override
    def start(self) -> None:
        if not self._file_path.exists():
            raise FileNotFoundError(f"Input file not found: {self._file_path}")

        ext = self._file_path.suffix.lower()

        if ext in _SUPPORTED_VIDEO_EXTS:
            self._read_video()
        elif ext in _SUPPORTED_IMAGE_EXTS:
            self._read_image()
        elif ext in _SUPPORTED_RAW_EXTS:
            self._read_raw()
        else:
            raise ValueError(
                f"Unsupported file type '{ext}'. "
                f"Supported: {_SUPPORTED_IMAGE_EXTS | _SUPPORTED_VIDEO_EXTS | _SUPPORTED_RAW_EXTS}"
            )

    # ── Private helpers ────────────────────────────────────────────────────────

    def _read_image(self) -> None:
        image: np.ndarray = cv2.imread(str(self._file_path))
        if image is None:
            raise OSError(f"cv2 could not read: {self._file_path}")
        self.outputs[0].send(IoData.from_image(image))
        self.outputs[0].send(IoData.end_of_stream())

    def _read_video(self) -> None:
        cap = cv2.VideoCapture(str(self._file_path))
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
        self.outputs[0].send(IoData.end_of_stream())

    def _read_raw(self) -> None:
        image: np.ndarray = rawpy.imread(str(self._file_path)).postprocess()
        self.outputs[0].send(IoData.from_image(image))
        self.outputs[0].send(IoData.end_of_stream())

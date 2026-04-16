from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import rawpy
from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import SourceNodeBase, NodeParam, NodeParamType
from core.port import OutputPort

_SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".cr2"}


class ImageSource(SourceNodeBase):
    """Source node that reads a single still image from disk.

    Supported formats: JPEG, PNG, CR2 (RAW).

    This source is *reactive*: the node editor automatically re-runs the
    flow whenever any parameter on any node is edited, so changes take
    effect immediately without pressing Run.

    Parameters:
      file_path -- path to the input image
    """

    def __init__(self) -> None:
        super().__init__("Image Source", section="Sources")
        self._file_path: Path = Path()
        self._add_output(OutputPort("image", {IoDataType.IMAGE}))
        self._apply_default_params()

    # ── Parameters ─────────────────────────────────────────────────────────────

    @property
    @override
    def params(self) -> list[NodeParam]:
        return [
            NodeParam("file_path", NodeParamType.FILE_PATH, {"default": "./input/example.jpg"}),
        ]

    @property
    def file_path(self) -> Path:
        return self._file_path

    @file_path.setter
    def file_path(self, path: str | Path) -> None:
        self._file_path = Path(path)

    # ── SourceNodeBase interface ────────────────────────────────────────────────

    @property
    @override
    def is_reactive(self) -> bool:
        return True

    @override
    def start(self) -> None:
        if not self._file_path.exists():
            raise FileNotFoundError(f"Input file not found: {self._file_path}")

        ext = self._file_path.suffix.lower()
        if ext not in _SUPPORTED_EXTS:
            raise ValueError(
                f"Unsupported file type '{ext}'. "
                f"Supported: {_SUPPORTED_EXTS}"
            )

        if ext == ".cr2":
            image: np.ndarray = rawpy.imread(str(self._file_path)).postprocess()
        else:
            image = cv2.imread(str(self._file_path))
            if image is None:
                raise OSError(f"cv2 could not read: {self._file_path}")

        self.outputs[0].send(IoData.from_image(image))
        self.outputs[0].send(IoData.end_of_stream())

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import rawpy
from typing_extensions import override

from constants import INPUT_DIR
from core.io_data import IoData, IoDataType
from core.node_base import SourceNodeBase, NodeParam, NodeParamType
from core.port import OutputPort

_SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".cr2"}


class ImageSource(SourceNodeBase):
    """Source node that reads a single still image from disk.

    Supported formats: JPEG, PNG, CR2 (RAW).

    Paths inside the application's :data:`INPUT_DIR` are stored — and
    therefore displayed — relative to that folder. Anything outside is kept
    as an absolute path. Relative paths are resolved against ``INPUT_DIR``
    at run time, which keeps saved flows portable across machines that
    share the same input layout.

    This source is *reactive*: the node editor automatically re-runs the
    flow whenever any parameter on any node is edited, so changes take
    effect immediately without pressing Run.

    Parameters:
      file_path -- path to the input image (relative to INPUT_DIR when possible)
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
            NodeParam("file_path", NodeParamType.FILE_PATH, {"default": "example.jpg", "filter": "Images (*.webp, *.png *.jpg *.jpeg *.cr2)"}),
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

    # ── SourceNodeBase interface ────────────────────────────────────────────────

    @property
    @override
    def is_reactive(self) -> bool:
        return True

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

        if ext == ".cr2":
            image: np.ndarray = rawpy.imread(str(resolved)).postprocess()
        else:
            image = cv2.imread(str(resolved))
            if image is None:
                raise OSError(f"cv2 could not read: {resolved}")

        self.outputs[0].send(IoData.from_image(image))

    # ── Internals ──────────────────────────────────────────────────────────────

    def _resolved_path(self) -> Path:
        """Return an absolute path; relative values are joined with INPUT_DIR."""
        if self._file_path.is_absolute():
            return self._file_path
        return INPUT_DIR / self._file_path

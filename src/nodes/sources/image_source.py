from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import rawpy
from typing_extensions import override

from constants import INPUT_DIR
from core.io_data import IoData, IoDataType, IoMeta
from core.node_base import SourceNodeBase
from core.params import FilePathParam
from core.path_utils import resolve_against
from core.port import OutputPort

_SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".cr2"}


class ImageSource(SourceNodeBase):
    """Source node that reads a single still image from disk.

    Supported formats: JPEG, PNG, WebP, CR2 (RAW). Paths inside
    :data:`INPUT_DIR` are stored relative to that folder so saved
    flows port cleanly across machines. Reactive: the flow re-runs
    on any parameter edit.
    """

    file_path = FilePathParam(
        "ship.jpg",
        constant=True,
        filter="Images (*.webp *.png *.jpg *.jpeg *.cr2)",
        base_dir=INPUT_DIR,
        description=(
            "Path to the input image. JPEG, PNG, WebP and CR2 (RAW) "
            "are supported. Paths inside the input folder are stored "
            "relative to it so the flow stays portable."
        ),
    )

    HEADER_ICON = "image"

    def __init__(self) -> None:
        super().__init__("Image Source", section="Sources")
        self._add_output(OutputPort("image", {IoDataType.IMAGE}))
        self._apply_default_params()

    @property
    @override
    def is_reactive(self) -> bool:
        return True

    @override
    def tick_count(self) -> int | None:
        return 1

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
            # cv2.imread() silently fails on Unicode paths on Windows; use
            # np.fromfile + imdecode to go through Python's wide-char I/O.
            # IMREAD_UNCHANGED preserves the alpha channel of RGBA PNGs /
            # WebPs so downstream nodes (Overlay, RgbaSplit) can use it.
            img_array = np.fromfile(resolved, dtype=np.uint8)
            image = cv2.imdecode(img_array, cv2.IMREAD_UNCHANGED)
            if image is None:
                raise OSError(f"cv2 could not read: {resolved}")
            # Normalise: greyscale → BGR, BGR/BGRA pass through as-is.
            # Everything downstream expects a 3- or 4-channel IMAGE.
            if image.ndim == 2:
                image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)

        self.outputs[0].send(
            IoData.from_image(image, meta=IoMeta(source_path=resolved))
        )

    def _resolved_path(self) -> Path:
        """Return an absolute path; relative values are joined with INPUT_DIR."""
        return resolve_against(self._file_path, INPUT_DIR)

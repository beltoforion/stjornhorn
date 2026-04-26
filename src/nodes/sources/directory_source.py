from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np
import rawpy
from typing_extensions import override

from constants import INPUT_DIR
from core.io_data import IoData, IoDataType
from core.node_base import SourceNodeBase, NodeParam, NodeParamType
from core.port import OutputPort

logger = logging.getLogger(__name__)

#: Image extensions DirectorySource will pick up. Mirrors ImageSource so a
#: directory full of mixed JPEG / PNG / WebP / CR2 files emits in the same
#: sort order regardless of which format any individual file uses.
_SUPPORTED_EXTS: frozenset[str] = frozenset({
    ".jpg", ".jpeg", ".png", ".webp", ".cr2",
})


class DirectorySource(SourceNodeBase):
    """Source node that emits every image file in a directory as a frame.

    Walks the configured directory in lexicographic order (top-down, with
    ``include_subdirectories`` controlling whether nested folders are
    visited) and emits each readable image as one ``IoData.IMAGE`` frame
    on the output port. Useful as a "video out of a folder of stills"
    fixture for testing temporal nodes, batch-processing screenshots, etc.

    Paths inside the application's :data:`INPUT_DIR` are stored — and
    therefore displayed — relative to that folder. Anything outside is
    kept as an absolute path. Relative paths are resolved against
    ``INPUT_DIR`` at run time, which keeps saved flows portable across
    machines that share the same input layout.

    Files whose extension is unsupported are skipped silently. Files with
    a supported extension that nonetheless fail to decode (corrupt,
    truncated, …) are logged and skipped so a single bad file doesn't
    abort the whole run. This source is **not** reactive — flipping a
    parameter shouldn't kick off a potentially long directory walk.

    Parameters:
      directory               -- folder to iterate over (relative to INPUT_DIR when possible)
      include_subdirectories  -- recurse into nested folders when True
    """

    def __init__(self) -> None:
        super().__init__("Directory Source", section="Sources")
        self._directory: Path = Path()
        self._include_subdirectories: bool = False
        self._add_output(OutputPort("image", {IoDataType.IMAGE}))
        self._apply_default_params()

    # ── Parameters ─────────────────────────────────────────────────────────────

    @property
    @override
    def params(self) -> list[NodeParam]:
        return [
            NodeParam(
                "directory",
                NodeParamType.FILE_PATH,
                {
                    "default":  "",
                    "mode":     "directory",
                    "base_dir": INPUT_DIR,
                    "caption":  "Select Image Directory",
                },
            ),
            NodeParam(
                "include_subdirectories",
                NodeParamType.BOOL,
                {"default": False},
            ),
        ]

    @property
    def directory(self) -> Path:
        return self._directory

    @directory.setter
    def directory(self, path: str | Path) -> None:
        p = Path(path)
        if p.is_absolute():
            try:
                p = p.resolve().relative_to(INPUT_DIR.resolve())
            except (OSError, ValueError):
                pass  # outside INPUT_DIR — keep absolute
        self._directory = p

    @property
    def include_subdirectories(self) -> bool:
        return self._include_subdirectories

    @include_subdirectories.setter
    def include_subdirectories(self, value: bool) -> None:
        self._include_subdirectories = bool(value)

    # ── SourceNodeBase interface ────────────────────────────────────────────────

    @override
    def process_impl(self) -> None:
        resolved = self._resolved_path()
        if not resolved.exists():
            raise FileNotFoundError(f"Input directory not found: {resolved}")
        if not resolved.is_dir():
            raise NotADirectoryError(f"Not a directory: {resolved}")

        for path in self._iter_image_files(resolved):
            image = self._load_image(path)
            if image is None:
                continue
            self.outputs[0].send(IoData.from_image(image))

    # ── Internals ──────────────────────────────────────────────────────────────

    def _resolved_path(self) -> Path:
        """Return an absolute path; relative values are joined with INPUT_DIR."""
        if self._directory.is_absolute():
            return self._directory
        return INPUT_DIR / self._directory

    def _iter_image_files(self, root: Path) -> list[Path]:
        """Return supported image files under *root* in lexicographic order.

        Sorted so the emitted frame order is deterministic across runs and
        across filesystems that don't guarantee a stable directory listing.
        """
        if self._include_subdirectories:
            candidates = (p for p in root.rglob("*") if p.is_file())
        else:
            candidates = (p for p in root.iterdir() if p.is_file())
        return sorted(
            p for p in candidates if p.suffix.lower() in _SUPPORTED_EXTS
        )

    @staticmethod
    def _load_image(path: Path) -> np.ndarray | None:
        """Decode *path*. Return ``None`` (and log) if it can't be read.

        Mirrors :class:`ImageSource` byte-for-byte so a directory walk
        accepts the exact same set of files a single ImageSource would,
        with the same Unicode-path-safe code path on Windows and the
        same RAW (.cr2) post-processing.
        """
        ext = path.suffix.lower()
        try:
            if ext == ".cr2":
                return rawpy.imread(str(path)).postprocess()

            img_array = np.fromfile(path, dtype=np.uint8)
            image = cv2.imdecode(img_array, cv2.IMREAD_UNCHANGED)
            if image is None:
                logger.warning("DirectorySource: could not decode %s", path)
                return None
            if image.ndim == 2:
                image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
            return image
        except (OSError, ValueError, RuntimeError) as exc:
            logger.warning(
                "DirectorySource: skipping unreadable file %s (%s)", path, exc,
            )
            return None

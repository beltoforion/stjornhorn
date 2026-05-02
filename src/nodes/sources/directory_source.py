from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

import cv2
import numpy as np
import rawpy
from typing_extensions import override

from constants import INPUT_DIR
from core.io_data import IoData, IoDataType, IoMeta
from core.node_base import SourceNodeBase
from core.params import BoolParam, FilePathParam
from core.path_utils import resolve_against
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

    Walks the directory in lexicographic order and emits each readable
    image as one frame. Useful as a "video out of a folder of stills"
    fixture. Unsupported extensions are skipped silently; supported
    files that fail to decode are logged and skipped. Paths inside
    :data:`INPUT_DIR` are stored relative to that folder. Not reactive
    — running on every parameter edit could trigger a long walk.
    """

    directory = FilePathParam(
        "",
        constant=True,
        mode="directory",
        base_dir=INPUT_DIR,
        caption="Select Image Directory",
    )
    include_subdirectories = BoolParam(False, constant=True)

    HEADER_ICON = "folder_open"

    def __init__(self) -> None:
        super().__init__("Directory Source", section="Sources")
        
        self._add_output(OutputPort("image", {IoDataType.IMAGE}))
        self._apply_default_params()

        # File-count cache for the header badge, keyed by
        # ``(path, include_subdirectories)`` so a toggle invalidates it.
        # Warmed by :meth:`on_flow_loaded`; refreshed lazily by
        # :meth:`tick_count` when the params change interactively.
        self._count_cache: tuple[tuple[str, bool], int] | None = None

    @override
    def on_flow_loaded(self) -> None:
        # Walk the directory at load time so the first paint doesn't
        # block on a stat-heavy directory listing.
        self._probe_file_count()

    @override
    def tick_count(self) -> int | None:
        return self._probe_file_count()

    @override
    def iter_frames(self) -> Iterator[None]:
        """Per-frame generator: one ``yield`` per decoded image file."""
        resolved = self._resolved_path()
        if not resolved.exists():
            raise FileNotFoundError(f"Input directory not found: {resolved}")
        if not resolved.is_dir():
            raise NotADirectoryError(f"Not a directory: {resolved}")

        for path in self._iter_image_files(resolved):
            image = self._load_image(path)
            if image is None:
                continue

            logger.debug(f"DirectorySource: emitting {path} ({image.shape})")

            # Stamp source_path so per-frame filename templating
            # (FileSink output_path = "$source_stem$.png", etc.) gets
            # one output file per input file. Without this, each
            # emit's meta is empty and a $source_stem$ template
            # collapses to a single overwriting filename.
            self.outputs[0].send(
                IoData.from_image(image, meta=IoMeta(source_path=path))
            )
            yield

    @override
    def process_impl(self) -> None:
        """Direct-invocation path: drain :meth:`iter_frames` in one call."""
        for _ in self.iter_frames():
            pass

    # ── Internals ──────────────────────────────────────────────────────────────

    def _resolved_path(self) -> Path:
        """Return an absolute path; relative values are joined with INPUT_DIR."""
        return resolve_against(self._directory, INPUT_DIR)

    def _probe_file_count(self) -> int | None:
        """Return the count of supported image files under the configured
        directory, cached by ``(path, include_subdirectories)``.

        Returns ``None`` for an unset / missing path so the header badge
        silently disappears rather than showing a misleading number.
        """
        try:
            path = self._resolved_path()
        except (TypeError, ValueError):
            return None
        
        if not path.is_dir():
            return None
        
        cache_key = (str(path), bool(self._include_subdirectories))
        if self._count_cache is not None and self._count_cache[0] == cache_key:
            return self._count_cache[1]
        try:
            count = len(self._iter_image_files(path))
        except OSError:
            return None
        
        self._count_cache = (cache_key, count)
        return count

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
                logger.warning(f"DirectorySource: could not decode {path}")
                return None
            if image.ndim == 2:
                image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
            return image
        except (OSError, ValueError, RuntimeError) as exc:
            logger.warning(
                f"DirectorySource: skipping unreadable file {path} ({exc})"
            )
            return None

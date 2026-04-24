from __future__ import annotations

import json
import logging
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from constants import USER_CONFIG_DIR

logger = logging.getLogger(__name__)

#: JSON file that persists the MRU list between sessions. Lives in the
#: same user-config directory as user-defined nodes.
_RECENT_FLOWS_FILE: Path = USER_CONFIG_DIR / "recent_flows.json"

#: Maximum number of recent paths kept in the list.
MAX_RECENT_FLOWS: int = 8


class RecentFlowsManager(QObject):
    """Persistent most-recently-used list of flow files.

    Stores up to :data:`MAX_RECENT_FLOWS` absolute paths in
    ``~/.image-inquest/recent_flows.json``.  Emits :attr:`changed`
    whenever the list is mutated so menus can rebuild themselves.

    The list is ordered newest-first.  Re-adding an existing path moves
    it to the top instead of creating a duplicate.
    """

    changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._paths: list[Path] = []
        self._load()

    # ── Access ────────────────────────────────────────────────────────────────

    @property
    def paths(self) -> list[Path]:
        """Return a snapshot of the current MRU list (newest first)."""
        return list(self._paths)

    def __len__(self) -> int:
        return len(self._paths)

    # ── Mutation ──────────────────────────────────────────────────────────────

    def add(self, path: Path) -> None:
        """Insert ``path`` at the top of the list (deduplicated, trimmed).

        Paths are resolved so the same file opened via different relative
        prefixes collapses to a single entry. Trimming keeps the list at
        :data:`MAX_RECENT_FLOWS` items.
        """
        resolved = _safe_resolve(path)
        self._paths = [p for p in self._paths if p != resolved]
        self._paths.insert(0, resolved)
        del self._paths[MAX_RECENT_FLOWS:]
        self._save()
        self.changed.emit()

    def remove(self, path: Path) -> None:
        """Drop ``path`` from the list if present (no-op otherwise)."""
        resolved = _safe_resolve(path)
        before = len(self._paths)
        self._paths = [p for p in self._paths if p != resolved]
        if len(self._paths) != before:
            self._save()
            self.changed.emit()

    def clear(self) -> None:
        if not self._paths:
            return
        self._paths = []
        self._save()
        self.changed.emit()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self) -> None:
        if not _RECENT_FLOWS_FILE.exists():
            return
        try:
            raw = _RECENT_FLOWS_FILE.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (OSError, json.JSONDecodeError):
            logger.exception("Failed to load %s; starting with empty MRU", _RECENT_FLOWS_FILE)
            return
        if not isinstance(data, list):
            logger.warning(
                "%s: expected JSON list, got %s; ignoring",
                _RECENT_FLOWS_FILE, type(data).__name__,
            )
            return
        parsed = [Path(item) for item in data if isinstance(item, str)][:MAX_RECENT_FLOWS]
        # Drop entries whose file has since been moved/deleted so the UI
        # never shows a recent flow the user can't actually open.
        existing = [p for p in parsed if p.exists()]
        self._paths = existing
        if len(existing) != len(parsed):
            logger.info(
                "Pruned %d missing entr%s from recent flows",
                len(parsed) - len(existing),
                "y" if len(parsed) - len(existing) == 1 else "ies",
            )
            self._save()

    def _save(self) -> None:
        try:
            _RECENT_FLOWS_FILE.parent.mkdir(parents=True, exist_ok=True)
            _RECENT_FLOWS_FILE.write_text(
                json.dumps([str(p) for p in self._paths], indent=2),
                encoding="utf-8",
            )
        except OSError:
            logger.exception("Failed to save %s", _RECENT_FLOWS_FILE)


def _safe_resolve(path: Path) -> Path:
    """Return ``path.resolve()`` but fall back to ``path`` on filesystem errors.

    ``Path.resolve()`` touches the filesystem, which can raise on broken
    symlinks or permission issues.  The MRU list still wants a stable
    key in those cases.
    """
    try:
        return path.resolve()
    except OSError:
        return path

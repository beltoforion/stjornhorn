from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QFileSystemWatcher
from PySide6.QtGui import QFont, QIcon, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit, QVBoxLayout, QWidget

from constants import LOG_FILE
from ui.icons import material_icon
from typing_extensions import override

from ui.page import PageBase, ToolbarSection

if TYPE_CHECKING:
    pass


# Upper bound on lines retained in the view. The full history stays on
# disk; older lines scroll off once this cap is reached so memory use
# stays bounded no matter how long the app runs.
_MAX_BLOCKS = 20_000

# Largest tail we seed the view with on first load or after rotation,
# so opening the page never blocks on a multi-megabyte read.
_TAIL_BYTES = 256 * 1024


class LogPage(PageBase):
    """Live-tail view of the application log file.

    Reads the file incrementally — only the bytes appended since the
    previous update are pulled in and inserted at the end. A
    :class:`QFileSystemWatcher` on both the file and its parent
    directory drives refreshes; watching the directory too lets us
    notice rotation, which renames the file out from under a per-file
    watch.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._offset: int = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._view = QPlainTextEdit(self)
        self._view.setReadOnly(True)
        self._view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._view.setMaximumBlockCount(_MAX_BLOCKS)
        mono = QFont()
        mono.setStyleHint(QFont.StyleHint.TypeWriter)
        mono.setFamily("Monospace")
        self._view.setFont(mono)
        root.addWidget(self._view)

        self._watcher = QFileSystemWatcher(self)
        self._watcher.fileChanged.connect(self._on_path_changed)
        self._watcher.directoryChanged.connect(self._on_path_changed)
        if LOG_FILE.parent.exists():
            self._watcher.addPath(str(LOG_FILE.parent))

        self._load_tail()
        self._install_file_watch()

    # ── Page hooks ─────────────────────────────────────────────────────────────

    @override
    def page_title(self) -> str:
        return "Log"

    @override
    def page_selector_label(self) -> str:
        return "Log"

    @override
    def page_selector_icon(self) -> QIcon:
        return material_icon("description")

    @override
    def page_toolbar_sections(self) -> list[ToolbarSection]:
        return []

    @override
    def on_activated(self) -> None:
        # Pick up anything that arrived while the page was hidden.
        self._refresh()

    # ── Internals ──────────────────────────────────────────────────────────────

    def _install_file_watch(self) -> None:
        if not LOG_FILE.exists():
            return
        path = str(LOG_FILE)
        if path not in self._watcher.files():
            self._watcher.addPath(path)

    def _load_tail(self) -> None:
        if not LOG_FILE.exists():
            self._offset = 0
            return
        try:
            size = LOG_FILE.stat().st_size
            with LOG_FILE.open("rb") as fh:
                if size > _TAIL_BYTES:
                    fh.seek(size - _TAIL_BYTES)
                    # Drop the partial first line so we start at a boundary.
                    fh.readline()
                chunk = fh.read()
                self._offset = fh.tell()
        except OSError:
            return
        self._append_bytes(chunk)

    def _on_path_changed(self, _path: str) -> None:
        self._refresh()

    def _refresh(self) -> None:
        if not LOG_FILE.exists():
            self._offset = 0
            return
        try:
            size = LOG_FILE.stat().st_size
        except OSError:
            return

        if size < self._offset:
            # File shrank → rotated or truncated. Start over.
            self._view.clear()
            self._offset = 0

        if size > self._offset:
            try:
                with LOG_FILE.open("rb") as fh:
                    fh.seek(self._offset)
                    chunk = fh.read()
                    self._offset = fh.tell()
            except OSError:
                return
            self._append_bytes(chunk)

        # Rotation drops the per-file watch (the inode was renamed);
        # re-add it so we keep receiving fileChanged signals.
        self._install_file_watch()

    def _append_bytes(self, data: bytes) -> None:
        if not data:
            return
        text = data.decode("utf-8", errors="replace")
        at_bottom = self._is_at_bottom()
        cursor = self._view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        if at_bottom:
            bar = self._view.verticalScrollBar()
            bar.setValue(bar.maximum())

    def _is_at_bottom(self) -> bool:
        bar = self._view.verticalScrollBar()
        return bar.value() >= bar.maximum() - 4

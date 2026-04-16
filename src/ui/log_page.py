from __future__ import annotations

import logging
from collections import deque
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QFont, QIcon
from PySide6.QtWidgets import QMenu, QPlainTextEdit, QVBoxLayout
from typing_extensions import override

from constants import LOG_FILE_PATH
from ui.icons import material_icon
from ui.page import PageBase, ToolbarSection

logger = logging.getLogger(__name__)

#: Maximum number of trailing log lines shown in the page.
MAX_LOG_LINES: int = 1000


class LogPage(PageBase):
    """Read-only viewer that shows the last :data:`MAX_LOG_LINES` lines
    of the application log file.

    The log is re-read on every activation and whenever the user triggers
    the Refresh action.  The text view uses a monospaced font so column-
    aligned log records stay aligned.  Missing or unreadable log files
    are surfaced inline so users can tell the page apart from an empty
    log at a glance.
    """

    def __init__(self) -> None:
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        # Fixed-width font so the "timestamp  LEVEL  logger  message"
        # columns produced by log.setup_logging line up.
        mono = QFont("Monospace")
        mono.setStyleHint(QFont.StyleHint.TypeWriter)
        self._text.setFont(mono)
        layout.addWidget(self._text, 1)

        self._refresh_action = QAction(material_icon("refresh"), "Refresh", self)
        self._refresh_action.setToolTip("Re-read the log file from disk")
        self._refresh_action.triggered.connect(self.refresh)

    # ── Page hooks ─────────────────────────────────────────────────────────────

    @override
    def page_selector_label(self) -> str:
        return "Log"

    @override
    def page_selector_icon(self) -> QIcon:
        return material_icon("article")

    @override
    def page_title(self) -> str:
        return ""

    @override
    def page_toolbar_sections(self) -> list[ToolbarSection]:
        return [ToolbarSection("Log", [self._refresh_action])]

    @override
    def page_menus(self) -> list[QMenu]:
        menu = QMenu("Log")
        menu.addAction(self._refresh_action)
        return [menu]

    @override
    def on_activated(self) -> None:
        # Always show fresh content when the user switches to this page.
        self.refresh()

    # ── Public API ─────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        """Reload the log file and display its last :data:`MAX_LOG_LINES` lines."""
        text = _read_tail(LOG_FILE_PATH, MAX_LOG_LINES)
        self._text.setPlainText(text)
        # Scroll to the end so the newest entry is immediately visible.
        cursor = self._text.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self._text.setTextCursor(cursor)
        # Also nudge the vertical scrollbar to the bottom in case the
        # cursor-based scroll lags on very large contents.
        bar = self._text.verticalScrollBar()
        bar.setValue(bar.maximum())


def _read_tail(path: Path, max_lines: int) -> str:
    """Return the last ``max_lines`` of the file at ``path``.

    Missing file → returns a short explanatory placeholder so the page
    isn't blank (a fresh install with no logs yet is common). Read
    errors are logged and surfaced in the view as well.
    """
    if not path.exists():
        return f"(no log file at {path})"
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fp:
            # Bounded buffer: keep the most recent ``max_lines`` without
            # loading the whole file into memory at once. At the
            # configured 1 MB rotation limit this is also safe to read
            # directly, but the deque approach is future-proof.
            buf: deque[str] = deque(maxlen=max_lines)
            for line in fp:
                buf.append(line)
    except OSError as err:
        logger.exception("Failed to read log file %s", path)
        return f"(failed to read {path}: {err})"

    if not buf:
        return "(log file is empty)"
    # Lines already include their trailing newlines; strip the very last
    # one so the QPlainTextEdit doesn't render a dangling empty row.
    return "".join(buf).rstrip("\n")

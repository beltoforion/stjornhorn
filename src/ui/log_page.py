from __future__ import annotations

from typing_extensions import override

from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from constants import USER_CONFIG_DIR
from ui.icons import material_icon
from ui.page import PageBase, ToolbarSection

_LOG_FILE = USER_CONFIG_DIR / "image-inquest.log"
_MAX_LINES = 1000


class LogPage(PageBase):
    """Page that displays the last :data:`_MAX_LINES` lines of the application log.

    The log file is read fresh every time the page is activated or the
    user clicks the Refresh toolbar button.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._refresh_action = QAction(
            material_icon("refresh"),
            "Refresh",
            self,
        )
        self._refresh_action.triggered.connect(self._load_log)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        font = self._text.font()
        font.setFamily("Monospace")
        font.setPointSize(9)
        self._text.setFont(font)
        root.addWidget(self._text)

    # ── PageBase interface ─────────────────────────────────────────────────────

    @override
    def page_selector_label(self) -> str:
        return "Log"

    @override
    def page_selector_icon(self) -> QIcon:
        return material_icon("description")

    def page_toolbar_sections(self) -> list[ToolbarSection]:
        return [ToolbarSection("Log", [self._refresh_action])]

    def on_activated(self) -> None:
        self._load_log()

    # ── Internals ──────────────────────────────────────────────────────────────

    def _load_log(self) -> None:
        """Read the last :data:`_MAX_LINES` lines from the log file."""
        if not _LOG_FILE.exists():
            self._text.setPlainText(f"Log file not found: {_LOG_FILE}")
            return
        try:
            content = _LOG_FILE.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            self._text.setPlainText(f"Could not read log file: {exc}")
            return

        lines = content.splitlines()
        if len(lines) > _MAX_LINES:
            lines = lines[-_MAX_LINES:]
        self._text.setPlainText("\n".join(lines))
        # Scroll to the bottom so the most recent entries are visible.
        self._text.moveCursor(self._text.textCursor().MoveOperation.End)

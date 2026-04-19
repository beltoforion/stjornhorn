from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from constants import APP_DISPLAY_NAME, APP_VERSION, FLOW_DIR
from core.flow import DEFAULT_FLOW_NAME, is_valid_flow_name
from ui.icons import material_icon
from typing_extensions import override

from ui.page import PageBase, ToolbarSection

if TYPE_CHECKING:
    pass


class LogPage(PageBase):
    """Page for displaying the log file
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(40, 60, 40, 40)
        root.setSpacing(12)

        title = QLabel(APP_DISPLAY_NAME)
        title_font = title.font()
        title_font.setPointSize(24)
        title_font.setBold(True)
        title.setFont(title_font)
        root.addWidget(title)

        version = QLabel(f"v{APP_VERSION}")
        version.setProperty("muted", True)
        root.addWidget(version)

        root.addSpacerItem(QSpacerItem(0, 20, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))

        row = QHBoxLayout()
        row.setSpacing(6)
        root.addLayout(row)

        # Open button.
        open_row = QHBoxLayout()
        open_row.addStretch(1)
        root.addLayout(open_row)

        root.addStretch(1)

    # ── Page hooks ─────────────────────────────────────────────────────────────

    def page_title(self) -> str:
        return ""  # MainWindow shows the bare app name on the start page

    @override
    def page_selector_label(self) -> str:
        return "Log"

    @override
    def page_selector_icon(self) -> QIcon:
        return material_icon("home")

    def page_toolbar_sections(self) -> list[ToolbarSection]:
        return []

    def on_activated(self) -> None:
        pass



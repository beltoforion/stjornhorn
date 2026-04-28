"""Settings page — single-screen view of persistent application options."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QCheckBox, QLabel, QVBoxLayout, QWidget
from typing_extensions import override

from ui.icons import material_icon
from ui.page import PageBase, ToolbarSection
from ui.settings import get_settings


class SettingsPage(PageBase):
    """Page exposing the user-facing application settings.

    The only setting today is "Enable debug logging", which controls
    whether the file log handler captures DEBUG records. Toggling the
    checkbox writes the new value to ``~/.image-inquest/settings.json``
    and applies it to the running logger immediately.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._settings = get_settings()

        root = QVBoxLayout(self)
        root.setContentsMargins(40, 40, 40, 40)
        root.setSpacing(16)
        root.setAlignment(Qt.AlignmentFlag.AlignTop)

        heading = QLabel("Settings")
        font = heading.font()
        font.setPointSize(18)
        font.setBold(True)
        heading.setFont(font)
        root.addWidget(heading)

        self._debug_logging_check = QCheckBox("Enable debug logging")
        self._debug_logging_check.setToolTip(
            "Capture DEBUG-level records in the application log file. "
            "Useful when reproducing a bug; leave off for normal use."
        )
        self._debug_logging_check.setChecked(self._settings.debug_logging)
        self._debug_logging_check.toggled.connect(self._on_debug_logging_toggled)
        root.addWidget(self._debug_logging_check)

    # ── Page hooks ─────────────────────────────────────────────────────────────

    @override
    def page_title(self) -> str:
        return "Settings"

    @override
    def page_selector_label(self) -> str:
        return "Settings"

    @override
    def page_selector_icon(self) -> QIcon:
        return material_icon("settings")

    @override
    def page_toolbar_sections(self) -> list[ToolbarSection]:
        return []

    # ── Callbacks ──────────────────────────────────────────────────────────────

    def _on_debug_logging_toggled(self, checked: bool) -> None:
        self._settings.debug_logging = checked

"""Settings page — single-screen view of persistent application options."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)
from typing_extensions import override

from ui.icons import material_icon
from ui.page import PageBase, ToolbarSection
from ui.settings import get_settings
from ui.theme import AVAILABLE_THEMES, get_active_theme


class SettingsPage(PageBase):
    """Page exposing the user-facing application settings.

    Currently surfaces:
      * **Theme** — picks the active visual theme. The selection is
        persisted to ``settings.json`` and applied on next launch
        (the theme is locked at module-import time, so a running
        process keeps using the previous theme until a restart).
      * **Enable debug logging** — toggles DEBUG-level capture in
        the file log handler.
    """

    #: Note appended next to the theme picker so the user knows the
    #: change won't take effect until the app is restarted. Themes
    #: are locked at ``ui.theme`` import time so widget code can
    #: rely on stable token values via ``from ui.theme import …``.
    _RESTART_HINT: str = "Takes effect on next launch."

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

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(8)

        # ── Theme picker ──
        self._theme_combo = QComboBox()
        for key, theme in AVAILABLE_THEMES.items():
            self._theme_combo.addItem(theme.display_name, userData=key)
        # Pre-select the persisted theme. Falls back to whatever the
        # active theme is (which already accounts for unknown names
        # in the file) so the combo never shows a missing entry.
        target = self._settings.theme_name
        idx = self._theme_combo.findData(target)
        if idx < 0:
            idx = self._theme_combo.findData(get_active_theme().name)
        self._theme_combo.setCurrentIndex(max(0, idx))
        self._theme_combo.currentIndexChanged.connect(self._on_theme_changed)

        theme_row = QHBoxLayout()
        theme_row.setSpacing(12)
        theme_row.addWidget(self._theme_combo)
        self._theme_hint = QLabel(self._RESTART_HINT)
        self._theme_hint.setProperty("muted", True)
        self._theme_hint.setVisible(False)
        theme_row.addWidget(self._theme_hint)
        theme_row.addStretch(1)
        theme_widget = QWidget()
        theme_widget.setLayout(theme_row)
        form.addRow("Theme:", theme_widget)

        root.addLayout(form)

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

    def _on_theme_changed(self, _index: int) -> None:
        key = self._theme_combo.currentData()
        if not isinstance(key, str):
            return
        self._settings.theme_name = key
        # Show the restart hint only once the user diverges from
        # whatever the currently-running app is rendering.
        diverges = key != get_active_theme().name
        self._theme_hint.setVisible(diverges)

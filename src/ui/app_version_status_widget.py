from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from constants import APP_DISPLAY_NAME, APP_VERSION


def _python_version_label() -> str:
    """Return the running Python version as ``Python X.Y.Z`` for display."""
    v = sys.version_info
    return f"Python {v.major}.{v.minor}.{v.micro}"


class AppVersionStatusWidget(QWidget):
    """Default page status widget: app name on top, version + runtime beneath.

    Three stacked right-aligned labels — the app name rendered at a
    larger size so it reads as the primary label, the application
    version muted beneath, and the active Python runtime muted below
    that. The triplet is vertically centred in the widget so it looks
    balanced next to the toolbar's 72 px action buttons.

    Kept as a small standalone class so every page can instantiate its
    own — two pages must not share the same QWidget instance, because
    QToolBar reparents widgets it hosts via ``QWidgetAction``.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(8, 0, 8, 0)
        outer.setSpacing(0)

        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addStretch(1)

        name = QLabel(APP_DISPLAY_NAME)
        name.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        name.setStyleSheet("font-size: 14pt;")

        version = QLabel(f"v{APP_VERSION}")
        version.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        version.setProperty("muted", True)

        python = QLabel(_python_version_label())
        python.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        python.setProperty("muted", True)

        column.addWidget(name)
        column.addWidget(version)
        column.addWidget(python)
        column.addStretch(1)
        outer.addLayout(column)

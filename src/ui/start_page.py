from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
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

from constants import APP_NAME, APP_VERSION, FLOW_DIR
from core.flow import DEFAULT_FLOW_NAME, is_valid_flow_name
from ui.page import Page

if TYPE_CHECKING:
    pass

_FLOW_FILE_FILTER = "Flow (*.flowjs);;All files (*)"


class StartPage(Page):
    """Landing page. Lets the user create a new flow by name or open an
    existing ``.flowjs`` file.

    The **Create** button is only enabled while the flow-name input
    contains a valid name (``a-zA-Z0-9_#+-``, non-empty).
    """

    create_flow_requested = Signal(str)     # emits flow name
    open_flow_requested   = Signal(Path)    # emits file path

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(40, 60, 40, 40)
        root.setSpacing(12)

        title = QLabel(APP_NAME)
        title_font = title.font()
        title_font.setPointSize(24)
        title_font.setBold(True)
        title.setFont(title_font)
        root.addWidget(title)

        version = QLabel(f"v{APP_VERSION}")
        version.setProperty("muted", True)
        root.addWidget(version)

        root.addSpacerItem(QSpacerItem(0, 20, QSizePolicy.Minimum, QSizePolicy.Fixed))

        # Name input + Create button.
        row = QHBoxLayout()
        row.setSpacing(6)
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText(DEFAULT_FLOW_NAME)
        self._name_input.setMinimumWidth(240)
        self._name_input.textChanged.connect(self._on_name_changed)
        self._name_input.returnPressed.connect(self._on_create_clicked)
        row.addWidget(self._name_input)

        self._create_button = QPushButton("Create")
        self._create_button.setEnabled(False)
        self._create_button.clicked.connect(self._on_create_clicked)
        row.addWidget(self._create_button)
        row.addStretch(1)
        root.addLayout(row)

        # Open button.
        open_row = QHBoxLayout()
        open_button = QPushButton("Open")
        open_button.clicked.connect(self._on_open_clicked)
        open_row.addWidget(open_button)
        open_row.addStretch(1)
        root.addLayout(open_row)

        root.addStretch(1)

    # ── Page hooks ─────────────────────────────────────────────────────────────

    def page_title(self) -> str:
        return ""  # MainWindow shows the bare app name on the start page

    def on_activated(self) -> None:
        self._name_input.setFocus(Qt.OtherFocusReason)
        self._name_input.selectAll()

    # ── Callbacks ──────────────────────────────────────────────────────────────

    def _on_name_changed(self, text: str) -> None:
        self._create_button.setEnabled(is_valid_flow_name(text))

    def _on_create_clicked(self) -> None:
        name = self._name_input.text()
        if not is_valid_flow_name(name):
            return
        self.create_flow_requested.emit(name)

    def _on_open_clicked(self) -> None:
        FLOW_DIR.mkdir(parents=True, exist_ok=True)
        path_str, _ = QFileDialog.getOpenFileName(
            self, "Open Flow", str(FLOW_DIR), _FLOW_FILE_FILTER,
        )
        if path_str:
            self.open_flow_requested.emit(Path(path_str))

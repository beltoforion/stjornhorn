from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from constants import APP_DISPLAY_NAME, APP_VERSION, FLOW_DIR
from core.flow import DEFAULT_FLOW_NAME, is_valid_flow_name
from ui.flow_layout import FlowLayout
from ui.icons import material_icon
from typing_extensions import override

from ui.page import PageBase, ToolbarSection

if TYPE_CHECKING:
    from ui.recent_flows import RecentFlowsManager

_FLOW_FILE_FILTER = "Flow (*.flowjs);;All files (*)"


class StartPage(PageBase):
    """Landing page. Lets the user create a new flow by name or open an
    existing ``.flowjs`` file.

    The **Create** button is only enabled while the flow-name input
    contains a valid name (``a-zA-Z0-9_#+-``, non-empty).
    """

    create_flow_requested = Signal(str)     # emits flow name
    open_flow_requested   = Signal(Path)    # emits file path

    #: Pixel side length of each recent-flow tile icon. Matches the grid
    #: spacing used by typical OS file explorers (just large enough for
    #: the text underneath to read comfortably).
    _RECENT_ICON_SIZE = 48
    _RECENT_TILE_WIDTH = 120

    def __init__(
        self,
        recent_flows: "RecentFlowsManager | None" = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._recent_flows = recent_flows

        # Toolbar action: mirrors the "Open" button in the body so the
        # start page contributes at least one item to the main toolbar.
        self._open_action = QAction(
            material_icon("folder_open"),
            "Open",
            self,
        )
        self._open_action.triggered.connect(self._on_open_clicked)

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
        open_row.addStretch(1)
        root.addLayout(open_row)

        # Recent flows wrap panel.
        root.addSpacerItem(QSpacerItem(0, 24, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))

        self._recent_heading = QLabel("Recent Flows")
        heading_font = self._recent_heading.font()
        heading_font.setPointSize(14)
        heading_font.setBold(True)
        self._recent_heading.setFont(heading_font)
        root.addWidget(self._recent_heading)

        self._recent_panel = QFrame()
        self._recent_panel.setFrameShape(QFrame.Shape.NoFrame)
        self._recent_layout = FlowLayout(self._recent_panel, margin=0, spacing=12)
        root.addWidget(self._recent_panel)

        self._recent_empty_label = QLabel("No recent flows")
        self._recent_empty_label.setProperty("muted", True)
        root.addWidget(self._recent_empty_label)

        self._rebuild_recent_tiles()
        if self._recent_flows is not None:
            self._recent_flows.changed.connect(self._rebuild_recent_tiles)

        root.addStretch(1)

    # ── Page hooks ─────────────────────────────────────────────────────────────

    def page_title(self) -> str:
        return ""  # MainWindow shows the bare app name on the start page

    @override
    def page_selector_label(self) -> str:
        return "Start"

    @override
    def page_selector_icon(self) -> QIcon:
        return material_icon("home")

    def page_toolbar_sections(self) -> list[ToolbarSection]:
        return [ToolbarSection("File", [self._open_action])]

    def on_activated(self) -> None:
        self._name_input.setFocus(Qt.FocusReason.OtherFocusReason)
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

    # ── Recent flows ───────────────────────────────────────────────────────────

    def _rebuild_recent_tiles(self) -> None:
        """Clear and repopulate the recent-flows wrap panel.

        Called once at construction and whenever the backing
        RecentFlowsManager emits ``changed``.
        """
        while (item := self._recent_layout.takeAt(0)) is not None:
            w = item.widget()
            if w is not None:
                w.deleteLater()

        paths = self._recent_flows.paths if self._recent_flows is not None else []
        for path in paths:
            self._recent_layout.addWidget(self._make_recent_tile(path))

        has_any = bool(paths)
        self._recent_panel.setVisible(has_any)
        self._recent_empty_label.setVisible(not has_any)

    def _make_recent_tile(self, path: Path) -> QToolButton:
        """Build a file-explorer-style tile (icon above label) for ``path``."""
        btn = QToolButton()
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        btn.setIcon(material_icon("description"))
        btn.setIconSize(QSize(self._RECENT_ICON_SIZE, self._RECENT_ICON_SIZE))
        btn.setAutoRaise(True)
        btn.setText(path.stem)
        btn.setToolTip(str(path))
        btn.setFixedWidth(self._RECENT_TILE_WIDTH)
        btn.clicked.connect(lambda _=False, p=path: self.open_flow_requested.emit(p))
        return btn

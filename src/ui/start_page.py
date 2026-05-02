from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QSize, Qt, QUrl, Signal
from PySide6.QtGui import QAction, QDesktopServices, QIcon
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from constants import (
    FLOW_DIR,
    WELCOME_HTML_PATH,
    WELCOME_PROBE_TIMEOUT_MS,
    WELCOME_URL_ONLINE,
)
from core.flow import DEFAULT_FLOW_NAME, is_valid_flow_name
from ui.flow_layout import FlowLayout
from ui.icons import material_icon
from ui.theme import get_active_theme
from typing_extensions import override

from ui.page import PageBase, ToolbarSection

if TYPE_CHECKING:
    from ui.recent_flows import RecentFlowsManager

_FLOW_FILE_FILTER = "Flow (*.flowjs);;All files (*)"


class _ExternalLinkPage(QWebEnginePage):
    """QWebEnginePage that routes link clicks out to the system browser.

    The welcome page lives inside a QWebEngineView but its buttons all
    point at external URLs (documentation site, GitHub). Without this
    indirection, regular link clicks would replace the welcome page in
    the embedded view, and ``target="_blank"`` clicks would silently no-op
    because the default ``createWindow`` returns a null page.

    Issue: #281
    """

    def __init__(
        self, parent: "QWidget | QWebEnginePage | None" = None, *, _popup: bool = False,
    ) -> None:
        super().__init__(parent)
        # Popup pages exist only to catch the URL of a target="_blank"
        # request (see ``createWindow``) and open it externally before any
        # network load actually happens. A non-popup page is the regular
        # welcome view, which serves the bundled / live welcome.html and
        # only diverts explicit link clicks.
        self._popup = _popup

    def acceptNavigationRequest(  # noqa: N802 — Qt override
        self, url: QUrl, nav_type: QWebEnginePage.NavigationType, is_main_frame: bool,
    ) -> bool:
        # Popup pages: every navigation is the user's link target. Hand
        # the URL straight to the OS — *before* any actual navigation
        # starts, so HSTS / browser scheme upgrades on the embedded
        # engine can't rewrite ``http://`` to ``https://`` first.
        if self._popup:
            QDesktopServices.openUrl(url)
            self.deleteLater()
            return False
        if nav_type == QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
            QDesktopServices.openUrl(url)
            return False
        return super().acceptNavigationRequest(url, nav_type, is_main_frame)

    def createWindow(  # noqa: N802 — Qt override
        self, _type: QWebEnginePage.WebWindowType,
    ) -> QWebEnginePage:
        # target="_blank" links route through createWindow, not
        # acceptNavigationRequest on this page. Return a throwaway page
        # whose acceptNavigationRequest catches the requested URL and
        # hands it to QDesktopServices.openUrl before any load occurs.
        return _ExternalLinkPage(self, _popup=True)


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

        # Row 1: welcome web view — soaks up all remaining vertical space.
        self._welcome_view = QWebEngineView()
        self._welcome_view.setPage(_ExternalLinkPage(self._welcome_view))
        self._welcome_view.settings().setAttribute(
            QWebEngineSettings.WebAttribute.ShowScrollBars, False,
        )
        # Push the active theme's colours into the page after every load
        # — both the initial bundled file load and a later swap to the
        # remote URL if the probe succeeds. The page itself ships with
        # placeholder CSS custom properties on :root; this re-binds them
        # so the welcome page tracks whatever theme the rest of the app
        # is wearing without requiring a parallel HTML variant per theme.
        self._welcome_view.loadFinished.connect(self._apply_theme_to_welcome)
        self._welcome_view.setUrl(QUrl.fromLocalFile(str(WELCOME_HTML_PATH)))
        root.addWidget(self._welcome_view, 1)
        self._probe_remote_welcome()

        # Row 2: create + recent flows, sized to content.
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

    # ── Welcome content ────────────────────────────────────────────────────────

    def _probe_remote_welcome(self) -> None:
        """Fire a short HEAD request to the public welcome URL and, on
        success, swap the view from the bundled file to the live page.

        The local file is loaded synchronously in ``__init__`` so the user
        always sees something immediately. When the host is unreachable
        (no internet, DNS failure, timeout, non-2xx response) we keep the
        local copy and never hit the network again for this session.
        """
        self._welcome_network = QNetworkAccessManager(self)
        request = QNetworkRequest(QUrl(WELCOME_URL_ONLINE))
        request.setTransferTimeout(WELCOME_PROBE_TIMEOUT_MS)
        reply = self._welcome_network.head(request)
        reply.finished.connect(lambda r=reply: self._on_remote_welcome_probed(r))

    def _apply_theme_to_welcome(self, ok: bool) -> None:
        """Push the active theme's colours into the welcome page.

        ``welcome.html`` is a single static file shared between every
        theme — its `:root` ships with placeholder CSS custom
        properties. After each load (bundled file or remote swap) we
        rebind those properties from the active :class:`Theme`, so
        backgrounds, panels, buttons, borders, accent colour and the
        per-category card headlines all track whatever the user picked
        on the Settings page.

        Issue: dynamic-theme-background
        """
        if not ok:
            return
        theme = get_active_theme()
        # Derive the welcome page's surface palette from the active theme:
        # use the app window colour as the page background, the button
        # colour as the raised "panel" surface (cards, buttons, kbd
        # chips), a slightly lightened version for hover states, and a
        # dimmer derivative of the window for divider lines.
        panel = theme.PALETTE_BUTTON
        css_vars = {
            "--bg":                theme.PALETTE_WINDOW.name(),
            "--bg-panel":          panel.name(),
            "--bg-panel-alt":      panel.lighter(120).name(),
            "--border":            theme.PALETTE_WINDOW.darker(135).name(),
            "--text":              theme.PALETTE_TEXT.name(),
            "--text-muted":        theme.STATUS_MUTED_COLOR.name(),
            "--accent":            theme.NODE_BORDER_SELECTED.name(),
            "--card-source-color": theme.SOURCE_HEADER_COLOR.name(),
            "--card-filter-color": theme.FILTER_HEADER_COLOR.name(),
            "--card-sink-color":   theme.SINK_HEADER_COLOR.name(),
        }
        # ``json.dumps`` on the dict gives us a JS-safe object literal
        # (proper string escaping, no risk of breaking the call if a
        # colour name ever contains a quote or backslash).
        js = (
            "(function(){"
            "var s=document.documentElement.style;"
            f"var v={json.dumps(css_vars)};"
            "for (var k in v) s.setProperty(k, v[k]);"
            "document.body.style.opacity='1';"
            "})();"
        )
        self._welcome_view.page().runJavaScript(js)

    def _on_remote_welcome_probed(self, reply: QNetworkReply) -> None:
        error = reply.error()
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        reply.deleteLater()
        if error != QNetworkReply.NetworkError.NoError:
            return
        if not isinstance(status, int) or not 200 <= status < 400:
            return
        self._welcome_view.setUrl(QUrl(WELCOME_URL_ONLINE))

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

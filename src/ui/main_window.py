from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (
    QMainWindow,
    QMenu,
    QMenuBar,
    QStackedWidget,
    QToolBar,
    QToolButton,
)

from constants import APP_DISPLAY_NAME, BUILTIN_NODES_DIR, USER_NODES_DIR
from core.flow import Flow
from core.node_registry import NodeRegistry
from ui.node_editor_page import NodeEditorPage
from ui.page import Page
from ui.start_page import StartPage

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Size of icons rendered inside every toolbar button.
_TOOLBAR_ICON_SIZE = QSize(20, 20)


class MainWindow(QMainWindow):
    """Top-level window. Hosts the page stack, the global menu bar, and
    the application toolbar.

    The toolbar is split into two regions:

    * a **page-selector** radio group (one checkable action per page),
      which swaps the active page when toggled, and
    * **page-specific actions** installed next to the selector,
      contributed by the active page via :meth:`Page.page_toolbar_actions`.

    MainWindow is the only place that knows about all pages. Each page
    contributes its own menus via :meth:`Page.page_menus` and its own
    toolbar items via :meth:`Page.page_toolbar_actions`; MainWindow
    clears and re-installs them on every page switch.
    """

    def __init__(self, initial_flow_path: Path | None = None) -> None:
        super().__init__()
        self.setWindowTitle(APP_DISPLAY_NAME)

        # ── Node registry ──
        self._registry = NodeRegistry()
        for err in self._registry.scan_builtin(BUILTIN_NODES_DIR):
            logger.warning("Built-in node scan: %s", err)
        for err in self._registry.scan_user(USER_NODES_DIR):
            logger.warning("User node scan: %s", err)
        logger.info("Registry: %d node(s) loaded", len(self._registry))

        # ── Page stack ──
        self._pages = QStackedWidget()
        self.setCentralWidget(self._pages)

        self._start_page  = StartPage()
        self._editor_page = NodeEditorPage(self._registry)
        # Seed the editor with an empty flow so the user can switch to it
        # via the page-selector radio group at any time without first
        # visiting the start page to create one.
        self._editor_page.set_flow(Flow())

        self._pages.addWidget(self._start_page)
        self._pages.addWidget(self._editor_page)

        # Wire page signals.
        self._start_page.create_flow_requested.connect(self._on_create_flow)
        self._start_page.open_flow_requested.connect(self._on_open_flow_from_start)
        for page in (self._start_page, self._editor_page):
            page.title_changed.connect(self._update_window_title)

        # ── Menu bar ──
        self._menu_bar: QMenuBar = self.menuBar()
        self._app_menu = self._build_app_menu()
        self._installed_page_menus: list[QMenu] = []

        # ── Toolbar ──
        self._toolbar = self._build_toolbar()
        self._installed_page_actions: list[QAction] = []
        self._page_separator: QAction | None = None

        self._page_selector_group = QActionGroup(self)
        self._page_selector_group.setExclusive(True)
        self._page_selector_actions: dict[Page, QAction] = {}
        for page in (self._start_page, self._editor_page):
            self._add_page_selector_action(page)
        # Separator between the page-selector radio group and the
        # page-specific toolbar actions.
        self._page_separator = self._toolbar.addSeparator()

        self._activate_page(self._start_page)

        # If a flow was supplied on the command line, jump straight into
        # the editor. Failure falls through to the start page (already
        # active) so a bad CLI arg never blocks app launch.
        if initial_flow_path is not None:
            if self._editor_page.load_flow(initial_flow_path):
                self._activate_page(self._editor_page)
            else:
                logger.warning(
                    "Could not load initial flow %s; staying on start page",
                    initial_flow_path,
                )

    # ── Page switching ─────────────────────────────────────────────────────────

    def _activate_page(self, page: Page) -> None:
        # Deactivate current.
        current = self._pages.currentWidget()
        if isinstance(current, Page) and current is not page:
            current.on_deactivated()

        # Swap.
        self._pages.setCurrentWidget(page)
        self._install_page_menus(page)
        self._install_page_toolbar_actions(page)
        selector = self._page_selector_actions.get(page)
        if selector is not None and not selector.isChecked():
            selector.setChecked(True)
        self._update_window_title(page.page_title())
        page.on_activated()

    def _install_page_menus(self, page: Page) -> None:
        # Remove previously-installed page menus. The app menu is persistent.
        for menu in self._installed_page_menus:
            self._menu_bar.removeAction(menu.menuAction())
            menu.deleteLater()
        self._installed_page_menus = []

        # Install the new page's menus. Do NOT call ``menu.setParent(menu_bar)``
        # — QMenuBar manages menus by their menuAction() and giving the QMenu
        # the menubar as its Qt parent corrupts popup handling and crashes on
        # first open. Holding a Python reference in ``_installed_page_menus``
        # keeps the menu alive for as long as it is attached.
        for menu in page.page_menus():
            self._menu_bar.addMenu(menu)
            self._installed_page_menus.append(menu)

    # ── Toolbar ────────────────────────────────────────────────────────────────

    def _build_toolbar(self) -> QToolBar:
        tb = QToolBar("Main", self)
        tb.setObjectName("MainToolbar")
        tb.setMovable(False)
        tb.setFloatable(False)
        tb.setIconSize(_TOOLBAR_ICON_SIZE)
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb)
        return tb

    def _add_page_selector_action(self, page: Page) -> None:
        action = QAction(page.page_selector_icon(), page.page_selector_label(), self)
        action.setCheckable(True)
        action.setToolTip(f"Switch to {page.page_selector_label()}")
        # ``toggled`` fires both for user clicks and for programmatic
        # ``setChecked`` calls; guard against re-entering _activate_page
        # when the selector is being driven from _activate_page itself.
        action.toggled.connect(lambda checked, p=page: self._on_page_selector_toggled(p, checked))
        self._page_selector_group.addAction(action)
        self._toolbar.addAction(action)
        self._page_selector_actions[page] = action

    def _on_page_selector_toggled(self, page: Page, checked: bool) -> None:
        if not checked:
            return
        if self._pages.currentWidget() is page:
            return
        self._activate_page(page)

    def _install_page_toolbar_actions(self, page: Page) -> None:
        # Remove previously-installed page-specific actions. These
        # QActions are owned by the page, so we only detach them from the
        # toolbar — do not deleteLater.
        for action in self._installed_page_actions:
            self._toolbar.removeAction(action)
        self._installed_page_actions = []

        for action in page.page_toolbar_actions():
            self._toolbar.addAction(action)
            self._installed_page_actions.append(action)

        self._apply_consistent_button_sizes()

    def _apply_consistent_button_sizes(self) -> None:
        """Force every QToolButton in the main toolbar to the same size.

        Computed as the max size hint across all buttons so the longest
        label (plus icon) fits, and every button matches.
        """
        buttons: list[QToolButton] = []
        for action in self._toolbar.actions():
            if action.isSeparator():
                continue
            widget = self._toolbar.widgetForAction(action)
            if isinstance(widget, QToolButton):
                # Clear any previously-set fixed size so sizeHint reflects
                # the button's natural content for the current action set.
                widget.setMinimumSize(0, 0)
                widget.setMaximumSize(16777215, 16777215)
                widget.adjustSize()
                buttons.append(widget)

        if not buttons:
            return

        max_w = max(b.sizeHint().width()  for b in buttons)
        max_h = max(b.sizeHint().height() for b in buttons)
        size  = QSize(max_w, max_h)
        for b in buttons:
            b.setFixedSize(size)

    # ── Menus ──────────────────────────────────────────────────────────────────

    def _build_app_menu(self) -> QMenu:
        """Always-visible application menu (Quit, About)."""
        menu = self._menu_bar.addMenu("&File")

        quit_action = QAction("&Quit", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        menu.addAction(quit_action)

        return menu

    # ── Navigation callbacks ───────────────────────────────────────────────────

    def _on_create_flow(self, name: str) -> None:
        flow = Flow(name=name)
        self._editor_page.set_flow(flow)
        self._activate_page(self._editor_page)

    def _on_open_flow_from_start(self, path: Path) -> None:
        ok = self._editor_page.load_flow(path)
        if ok:
            self._activate_page(self._editor_page)
        # On failure stay on the start page (status label won't help there
        # today; a follow-up could surface the error via QMessageBox).

    def _update_window_title(self, page_title: str) -> None:
        if page_title:
            self.setWindowTitle(f"{APP_DISPLAY_NAME} — {page_title}")
        else:
            self.setWindowTitle(APP_DISPLAY_NAME)

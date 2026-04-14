from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QMainWindow,
    QMenu,
    QMenuBar,
    QStackedWidget,
)

from constants import APP_NAME, BUILTIN_NODES_DIR, USER_NODES_DIR
from core.flow import Flow
from core.node_registry import NodeRegistry
from ui.node_editor_page import NodeEditorPage
from ui.page import Page
from ui.start_page import StartPage

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Top-level window. Hosts the page stack and the global menu bar.

    MainWindow is the only place that knows about all pages. Each page
    contributes its own menus via :meth:`Page.page_menus`; MainWindow
    clears and re-installs them on every page switch.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)

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

        self._pages.addWidget(self._start_page)
        self._pages.addWidget(self._editor_page)

        # Wire page signals.
        self._start_page.create_flow_requested.connect(self._on_create_flow)
        self._start_page.open_flow_requested.connect(self._on_open_flow_from_start)
        self._editor_page.back_requested.connect(self._go_to_start)
        for page in (self._start_page, self._editor_page):
            page.title_changed.connect(self._update_window_title)

        # ── Menu bar ──
        self._menu_bar: QMenuBar = self.menuBar()
        self._app_menu = self._build_app_menu()
        self._installed_page_menus: list[QMenu] = []

        self._activate_page(self._start_page)

    # ── Page switching ─────────────────────────────────────────────────────────

    def _activate_page(self, page: Page) -> None:
        # Deactivate current.
        current = self._pages.currentWidget()
        if isinstance(current, Page) and current is not page:
            current.on_deactivated()

        # Swap.
        self._pages.setCurrentWidget(page)
        self._install_page_menus(page)
        self._update_window_title(page.page_title())
        page.on_activated()

    def _install_page_menus(self, page: Page) -> None:
        # Remove previously-installed page menus. The app menu is persistent.
        for menu in self._installed_page_menus:
            self._menu_bar.removeAction(menu.menuAction())
        self._installed_page_menus = []

        # Install new page's menus before the Help menu (by inserting
        # actions in order: each page menu goes at the end before Help).
        for menu in page.page_menus():
            # Re-parent so the menu's signals are owned by this window.
            menu.setParent(self._menu_bar)
            self._menu_bar.addMenu(menu)
            self._installed_page_menus.append(menu)

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

    def _go_to_start(self) -> None:
        # Reset the editor so returning to it doesn't show stale nodes.
        self._editor_page.set_flow(Flow())
        self._activate_page(self._start_page)

    def _update_window_title(self, page_title: str) -> None:
        if page_title:
            self.setWindowTitle(f"{APP_NAME} — {page_title}")
        else:
            self.setWindowTitle(APP_NAME)

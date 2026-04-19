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
from ui.page import PageBase
from ui.recent_flows import RecentFlowsManager
from ui.start_page import StartPage
from ui.log_page import LogPage

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Icon size and fixed button dimensions for the main toolbar.
_TOOLBAR_ICON_SIZE   = QSize(40, 40)
_TOOLBAR_BUTTON_SIZE = QSize(72, 72)


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

        # ── Recent flows MRU (persistent across sessions) ──
        self._recent_flows = RecentFlowsManager(self)
        self._recent_flows.changed.connect(self._rebuild_recent_menu)

        # ── Page stack ──
        self._pages = QStackedWidget()
        self.setCentralWidget(self._pages)

        self._start_page  = StartPage()
        self._editor_page = NodeEditorPage(self._registry, self._recent_flows)
        self._log_page    = LogPage()

        # Single source of truth for the set of pages. Adding a new page
        # means: construct it, append it here, and every loop below —
        # stack registration, signal wiring, page-selector actions —
        # picks it up automatically.
        self._pages_list: list[PageBase] = [
            self._start_page,
            self._editor_page,
            self._log_page,
        ]

        for page in self._pages_list:
            self._pages.addWidget(page)
            page.title_changed.connect(self._update_window_title)

        # Per-page signals that only make sense on one page live outside
        # the iteration above.
        self._start_page.create_flow_requested.connect(self._on_create_flow)
        self._start_page.open_flow_requested.connect(self._on_open_flow_from_start)

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
        self._page_selector_actions: dict[PageBase, QAction] = {}
        for page in self._pages_list:
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

    def _activate_page(self, page: PageBase) -> None:
        # Deactivate current.
        current = self._pages.currentWidget()
        if isinstance(current, PageBase) and current is not page:
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

    def _install_page_menus(self, page: PageBase) -> None:
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
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb)
        return tb

    def _add_page_selector_action(self, page: PageBase) -> None:
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

    def _on_page_selector_toggled(self, page: PageBase, checked: bool) -> None:
        if not checked:
            return
        if self._pages.currentWidget() is page:
            return
        self._activate_page(page)

    def _install_page_toolbar_actions(self, page: PageBase) -> None:
        # Remove previously-installed page-specific items (actions and
        # separators). QActions are owned by the page, so we only detach
        # them from the toolbar — do not deleteLater. Separators are
        # owned by us, so we delete them.
        for item in self._installed_page_actions:
            self._toolbar.removeAction(item)
            if item.isSeparator():
                item.deleteLater()
        self._installed_page_actions = []

        for i, section in enumerate(page.page_toolbar_sections()):
            if i > 0:
                sep = self._toolbar.addSeparator()
                self._installed_page_actions.append(sep)
            for action in section.actions:
                self._toolbar.addAction(action)
                self._installed_page_actions.append(action)

        self._apply_consistent_button_sizes()

    def _apply_consistent_button_sizes(self) -> None:
        """Apply a uniform fixed size to every QToolButton in the main toolbar."""
        for action in self._toolbar.actions():
            if action.isSeparator():
                continue
            widget = self._toolbar.widgetForAction(action)
            if isinstance(widget, QToolButton):
                widget.setFixedSize(_TOOLBAR_BUTTON_SIZE)

    # ── Menus ──────────────────────────────────────────────────────────────────

    def _build_app_menu(self) -> QMenu:
        """Always-visible application menu (Recently Used Files, Quit)."""
        menu = self._menu_bar.addMenu("&File")

        # MRU submenu: rebuilt on every RecentFlowsManager.changed emission
        # so the labels reflect the latest state without any per-open hook.
        self._recent_menu = menu.addMenu("Recently Used Files")
        self._rebuild_recent_menu()
        menu.addSeparator()

        quit_action = QAction("&Quit", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        menu.addAction(quit_action)

        return menu

    def _rebuild_recent_menu(self) -> None:
        """Repopulate the Recently Used Files submenu from the MRU list.

        Called once at startup and on every :attr:`RecentFlowsManager.changed`
        emission. Disabled placeholder ("(none)") shown when the list is
        empty; a trailing "Clear Recent Files" action lets the user wipe
        the MRU from the UI without editing the JSON file by hand.
        """
        self._recent_menu.clear()
        paths = self._recent_flows.paths
        if not paths:
            empty = QAction("(none)", self)
            empty.setEnabled(False)
            self._recent_menu.addAction(empty)
            return
        for index, path in enumerate(paths, start=1):
            # Leading "&N " gives Alt-N mnemonics for the first 9 entries.
            label = f"&{index} {path.name}" if index < 10 else path.name
            action = QAction(label, self)
            action.setToolTip(str(path))
            action.triggered.connect(lambda _checked=False, p=path: self._on_open_recent(p))
            self._recent_menu.addAction(action)
        self._recent_menu.addSeparator()
        clear = QAction("Clear Recent Files", self)
        clear.triggered.connect(self._recent_flows.clear)
        self._recent_menu.addAction(clear)

    def _on_open_recent(self, path: Path) -> None:
        """Load ``path`` in the editor and switch to the editor page.

        On failure the editor page already shows a status message and the
        path is dropped from the MRU so the user doesn't keep seeing a
        stale entry.
        """
        if self._editor_page.load_flow(path):
            self._activate_page(self._editor_page)
        else:
            self._recent_flows.remove(path)

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

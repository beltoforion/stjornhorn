from __future__ import annotations

import json
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

from constants import APP_DISPLAY_NAME, BUILTIN_NODES_DIR, USER_CONFIG_DIR, USER_NODES_DIR
from core.flow import Flow
from core.node_registry import NodeRegistry
from ui.node_editor_page import NodeEditorPage
from ui.page import PageBase
from ui.start_page import StartPage

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Icon size and fixed button dimensions for the main toolbar.
_TOOLBAR_ICON_SIZE   = QSize(40, 40)
_TOOLBAR_BUTTON_SIZE = QSize(72, 72)

_RECENT_FILES_PATH = USER_CONFIG_DIR / "recent_flows.json"
_MAX_RECENT_FILES  = 5


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
        self._editor_page.flow_opened.connect(self._on_flow_opened)

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
        """Always-visible application menu (Recent Files, Quit)."""
        menu = self._menu_bar.addMenu("&File")

        self._recent_menu = menu.addMenu("Recently Used Files")
        self._refresh_recent_menu()

        menu.addSeparator()

        quit_action = QAction("&Quit", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        menu.addAction(quit_action)

        return menu

    # ── Recently used files ────────────────────────────────────────────────────

    def _load_recent_files(self) -> list[Path]:
        """Return the persisted recently-used flow paths (most recent first)."""
        try:
            data = json.loads(_RECENT_FILES_PATH.read_text(encoding="utf-8"))
            return [Path(p) for p in data if isinstance(p, str)]
        except Exception:
            return []

    def _save_recent_files(self, paths: list[Path]) -> None:
        """Persist *paths* to disk, creating the config directory if needed."""
        try:
            USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            _RECENT_FILES_PATH.write_text(
                json.dumps([str(p) for p in paths], indent=2),
                encoding="utf-8",
            )
        except Exception:
            logger.warning("Could not save recent files list", exc_info=True)

    def _add_to_recent(self, path: Path) -> None:
        """Prepend *path* to the recent files list (max 5 entries, no duplicates)."""
        recent = [p for p in self._load_recent_files() if p != path]
        recent.insert(0, path)
        recent = recent[:_MAX_RECENT_FILES]
        self._save_recent_files(recent)
        self._refresh_recent_menu()

    def _refresh_recent_menu(self) -> None:
        """Rebuild the Recently Used Files submenu from persisted data."""
        self._recent_menu.clear()
        recent = self._load_recent_files()
        if not recent:
            placeholder = QAction("(empty)", self)
            placeholder.setEnabled(False)
            self._recent_menu.addAction(placeholder)
            return
        for path in recent:
            action = QAction(path.name, self)
            action.setToolTip(str(path))
            action.triggered.connect(lambda checked=False, p=path: self._open_recent(p))
            self._recent_menu.addAction(action)

    def _open_recent(self, path: Path) -> None:
        """Load a recently used flow and switch to the editor."""
        if not path.exists():
            logger.warning("Recent file no longer exists: %s", path)
            self._refresh_recent_menu()
            return
        ok = self._editor_page.load_flow(path)
        if ok:
            self._activate_page(self._editor_page)

    def _on_flow_opened(self, path: Path) -> None:
        """Called whenever the editor successfully loads a flow from disk."""
        self._add_to_recent(path)

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

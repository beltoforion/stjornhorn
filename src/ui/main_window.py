import logging

import dearpygui.dearpygui as dpg

from constants import BUILTIN_NODES_DIR, USER_NODES_DIR
from core.node_registry import NodeRegistry
from ui._types import DpgTag
from ui.dpg_themes import DpgThemes
from ui.node_editor_page import NodeEditorPage
from ui.page_manager import PageManager
from ui.start_page import StartPage

logger = logging.getLogger(__name__)


class MainWindow:
    def __init__(self):
        self._window_tag: DpgTag = dpg.generate_uuid()
        self._menu_tag:   DpgTag = dpg.generate_uuid()

        # Empty viewport menu bar; pages populate it on activation.
        dpg.add_viewport_menu_bar(tag=self._menu_tag)

        registry = NodeRegistry()
        for err in registry.scan_builtin(BUILTIN_NODES_DIR):
            logger.warning("Built-in node scan: %s", err)
        for err in registry.scan_user(USER_NODES_DIR):
            logger.warning("User node scan: %s", err)
        logger.info("Registry: %d node(s) loaded", len(registry))

        # One shared theme bundle for every page.
        self._themes = DpgThemes()

        self._pages = PageManager()
        with dpg.window(tag=self._window_tag):
            self._pages.register(StartPage(
                parent=self._window_tag,
                menu_bar=self._menu_tag,
                page_manager=self._pages,
                themes=self._themes,
            ))
            self._pages.register(NodeEditorPage(
                parent=self._window_tag,
                menu_bar=self._menu_tag,
                page_manager=self._pages,
                registry=registry,
                themes=self._themes,
            ))
        self._pages.activate(self._pages.start_page)

    @property
    def window_tag(self) -> DpgTag:
        return self._window_tag

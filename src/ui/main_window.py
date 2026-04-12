import dearpygui.dearpygui as dpg

from constants import BUILTIN_NODES_DIR, USER_NODES_DIR
from core.node_registry import NodeRegistry
from ui.node_editor_page import NodeEditorPage
from ui.page_manager import PageManager
from ui.start_page import StartPage


class MainWindow:
    def __init__(self):
        self._window_tag: int | str = dpg.generate_uuid()
        self._menu_tag:   int | str = dpg.generate_uuid()

        with dpg.window(tag=self._window_tag):
            pass

        with dpg.viewport_menu_bar(tag=self._menu_tag):
            with dpg.menu(label="File"):
                dpg.add_menu_item(label="New",     callback=self._on_new)
                dpg.add_menu_item(label="Save As", callback=self._on_save)

        registry = NodeRegistry()
        registry.scan_builtin(BUILTIN_NODES_DIR)
        registry.scan_user(USER_NODES_DIR)

        self._pages = PageManager()
        self._pages.register(StartPage(
            parent=self._window_tag,
            menu_bar=self._menu_tag,
            page_manager=self._pages,
        ))
        self._pages.register(NodeEditorPage(
            parent=self._window_tag,
            menu_bar=self._menu_tag,
            page_manager=self._pages,
            registry=registry,
        ))
        self._pages.activate(self._pages.start_page)

    @property
    def window_tag(self) -> int | str:
        return self._window_tag

    def _on_new(self, sender):
        print(f"New: {sender}")

    def _on_save(self, sender):
        print(f"Save As: {sender}")

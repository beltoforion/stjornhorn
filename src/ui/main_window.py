import dearpygui.dearpygui as dpg

from ui.node_editor_page import NodeEditorPage
from ui.page_manager import PageManager
from ui.start_page import StartPage


class MainWindow:
    def __init__(self):
        with dpg.window(label="App", tag="main_window"):
            pass

        with dpg.viewport_menu_bar(tag="main_menu"):
            with dpg.menu(label="File"):
                dpg.add_menu_item(label="New", callback=self._on_new)
                dpg.add_menu_item(label="Save As", callback=self._on_save)

        self._pages = PageManager()
        self._pages.register("start", StartPage(
            parent="main_window",
            menu_bar="main_menu",
            on_create_flow=self._goto_editor,
        ))
        self._pages.register("editor", NodeEditorPage(
            parent="main_window",
            menu_bar="main_menu",
            on_exit=self._goto_start,
        ))
        self._pages.activate("start")

    def _goto_editor(self) -> None:
        self._pages.activate("editor")

    def _goto_start(self) -> None:
        self._pages.activate("start")

    def _on_new(self, sender):
        print(f"New: {sender}")

    def _on_save(self, sender):
        print(f"Save As: {sender}")

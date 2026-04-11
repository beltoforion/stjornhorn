import dearpygui.dearpygui as dpg

from ui.node_editor import NodeEditor
from ui.start_page import StartPage


class MainWindow:
    def __init__(self):
        with dpg.window(label="App", tag="main_window"):
            self._start_page = StartPage(parent="main_window", on_flow_selected=self._open_flow)

            with dpg.child_window(tag="editor_page", show=False, border=False):
                self._node_editor = NodeEditor(parent="editor_page")

        with dpg.viewport_menu_bar(tag="main_menu"):
            with dpg.menu(label="File"):
                dpg.add_menu_item(label="New", callback=self._on_new)
                dpg.add_menu_item(label="Save As", callback=self._on_save)

        self._node_editor.add_menu("main_menu")
        dpg.hide_item("node_editor_menu")

    def _open_flow(self, path: str) -> None:
        self._start_page.hide()
        dpg.show_item("editor_page")
        dpg.show_item("node_editor_menu")

    def _on_new(self, sender):
        print(f"New: {sender}")

    def _on_save(self, sender):
        print(f"Save As: {sender}")

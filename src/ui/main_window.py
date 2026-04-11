import dearpygui.dearpygui as dpg

from ui.node_editor import *


class MainWindow:
    def __init__(self):
        with dpg.window(label="App", tag="main_window"):
            self._node_editor : NodeEditor = NodeEditor(parent="main_window")

            with dpg.viewport_menu_bar(tag="main_menu"):
                with dpg.menu(label="File"):
                    dpg.add_menu_item(label="New", callback=self._on_new)
                    dpg.add_menu_item(label="Save As", callback=self._on_save)

        self._node_editor.add_menu("main_menu")

    def _on_new(self, sender): 
        print(f"New: {sender}")

    def _on_save(self, sender): 
        print(f"Save As: {sender}")


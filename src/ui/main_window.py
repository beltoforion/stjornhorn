import dearpygui.dearpygui as dpg

from core.flow import Flow
from ui.node_editor_page import NodeEditorPage
from ui.page_manager import PageManager
from ui.start_page import StartPage


class MainWindow:
    def __init__(self):
        self._window_tag: int = dpg.generate_uuid()
        self._menu_tag: int = dpg.generate_uuid()

        with dpg.window(tag=self._window_tag):
            pass

        with dpg.viewport_menu_bar(tag=self._menu_tag):
            with dpg.menu(label="File"):
                dpg.add_menu_item(label="New", callback=self._on_new)
                dpg.add_menu_item(label="Save As", callback=self._on_save)

        self._start_page = StartPage(
            parent=self._window_tag,
            menu_bar=self._menu_tag,
            on_create_flow=self._open_flow,
            on_load_flow=self._on_load_flow,
        )
        self._node_editor_page = NodeEditorPage(
            parent=self._window_tag,
            menu_bar=self._menu_tag,
            on_exit=self._close_flow,
        )

        self._pages = PageManager()
        self._pages.register(self._start_page)
        self._pages.register(self._node_editor_page)
        self._pages.activate(self._start_page)

    @property
    def window_tag(self) -> int:
        return self._window_tag

    def _open_flow(self, flow: Flow) -> None:
        self._node_editor_page.set_flow(flow)
        self._pages.activate(self._node_editor_page)

    def _close_flow(self) -> None:
        self._pages.activate(self._start_page)

    def _on_load_flow(self) -> None:
        # TODO: implement flow loading (file dialog + deserialization).
        print("Load Flow: not implemented yet")

    def _on_new(self, sender):
        print(f"New: {sender}")

    def _on_save(self, sender):
        print(f"Save As: {sender}")

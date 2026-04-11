import dearpygui.dearpygui as dpg

from core.flow import Flow
from ui.page import Page


class StartPage(Page):
    def __init__(self, parent: str, menu_bar: str, on_create_flow, on_load_flow) -> None:
        self._on_create_flow = on_create_flow
        self._on_load_flow = on_load_flow
        super().__init__(parent=parent, menu_bar=menu_bar)

    def _build_ui(self) -> None:
        with dpg.child_window(tag=self._content_tag, parent=self._parent, border=False, show=False):
            dpg.add_spacer(height=60)
            dpg.add_text("Image Inquest", indent=20)
            dpg.add_spacer(height=20)
            with dpg.group(horizontal=True, indent=20):
                dpg.add_button(label="New Flow", callback=self._on_new_flow_clicked)
                dpg.add_button(label="Load Flow", callback=self._on_load_flow_clicked)

    def _install_menus(self) -> None:
        # Start page contributes no menus of its own.
        pass

    def _on_new_flow_clicked(self, sender) -> None:
        self._on_create_flow(Flow())

    def _on_load_flow_clicked(self, sender) -> None:
        self._on_load_flow()

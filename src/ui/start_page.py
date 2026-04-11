from __future__ import annotations

from typing import TYPE_CHECKING

import dearpygui.dearpygui as dpg

from core.flow import Flow
from ui.page import Page

if TYPE_CHECKING:
    from ui.page_manager import PageManager


class StartPage(Page):
    name = "start"

    def __init__(self, parent: int | str, menu_bar: int | str, page_manager: PageManager) -> None:
        super().__init__(parent=parent, menu_bar=menu_bar, page_manager=page_manager)

    def _build_ui(self) -> None:
        with dpg.child_window(tag=self._content_tag, parent=self._parent, border=False, show=False):
            dpg.add_spacer(height=60)
            dpg.add_text("Image Inquest", indent=20)
            dpg.add_spacer(height=20)
            with dpg.group(horizontal=True, indent=20):
                dpg.add_button(label="New Flow", callback=self._on_new_flow_clicked)
                dpg.add_button(label="Load Flow", callback=self._on_load_flow_clicked)

    def _install_menus(self) -> None:
        pass

    def _on_new_flow_clicked(self, sender) -> None:
        self._page_manager.editor_page.set_flow(Flow())
        self._page_manager.activate(self._page_manager.editor_page)

    def _on_load_flow_clicked(self, sender) -> None:
        # TODO: implement flow loading (file dialog + deserialization).
        print("Load Flow: not implemented yet")

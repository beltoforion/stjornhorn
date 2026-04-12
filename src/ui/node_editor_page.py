from __future__ import annotations

from typing import TYPE_CHECKING

import dearpygui.dearpygui as dpg

from core.flow import Flow
from ui.page import Page

if TYPE_CHECKING:
    from ui.page_manager import PageManager


class NodeEditorPage(Page):
    name = "editor"

    def __init__(self, parent: int | str, menu_bar: int | str, page_manager: PageManager) -> None:
        self._node_editor_tag: int | str = dpg.generate_uuid()
        self._node_count: int = 0
        self._flow: Flow | None = None
        super().__init__(parent=parent, menu_bar=menu_bar, page_manager=page_manager)

    def set_flow(self, flow: Flow) -> None:
        self._flow = flow

    def _build_ui(self) -> None:
        dpg.add_spacer(height=20)
        with dpg.group(horizontal=True):
            dpg.add_button(label="Add Node", callback=self._on_add_node)
            dpg.add_button(label="Clear All", callback=self._on_clear_nodes)
        dpg.add_node_editor(
            tag=self._node_editor_tag,
            callback=self._link,
            delink_callback=self._delink,
            height=-1,
        )

    def _install_menus(self) -> None:
        menu_tag = dpg.generate_uuid()
        with dpg.menu(label="Node Editor", parent=self._menu_bar, tag=menu_tag):
            dpg.add_menu_item(label="Add Node", callback=self._on_add_node)
            dpg.add_menu_item(label="Clear All", callback=self._on_clear_nodes)
            dpg.add_separator()
            dpg.add_menu_item(label="Exit", callback=self._on_exit_clicked)
        self._menu_tags.append(menu_tag)

    def _add_node(self, label: str, attr_in: str, attr_out: str, width: int) -> None:
        with dpg.node(label=label, parent=self._node_editor_tag):
            with dpg.node_attribute(label=attr_in):
                dpg.add_input_float(label="F", width=width)
            with dpg.node_attribute(label=attr_out, attribute_type=dpg.mvNode_Attr_Output):
                dpg.add_input_float(label="F", width=width)

    def _link(self, sender, app_data) -> None:
        dpg.add_node_link(app_data[0], app_data[1], parent=sender)

    def _delink(self, sender, app_data) -> None:
        dpg.delete_item(app_data)

    def _clear_nodes(self) -> None:
        children = dpg.get_item_children(self._node_editor_tag, 1)
        if children is None:
            return
        for child in children:
            dpg.delete_item(child)
        self._node_count = 0

    def _on_add_node(self, sender) -> None:
        self._node_count += 1
        n = self._node_count
        self._add_node(
            label=f"Node {n}",
            attr_in=f"attr_in_{n}",
            attr_out=f"attr_out_{n}",
            width=200,
        )

    def _on_clear_nodes(self, sender) -> None:
        self._clear_nodes()

    def _on_exit_clicked(self, sender) -> None:
        self._clear_nodes()
        self._page_manager.activate(self._page_manager.start_page)

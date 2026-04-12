from __future__ import annotations

from typing import TYPE_CHECKING

import dearpygui.dearpygui as dpg

from core.flow import Flow
from core.node_base import NodeBase, NodeParam, NodeParamType
from nodes.sources.file_source import FileSource
from ui.page import Page

if TYPE_CHECKING:
    from ui.page_manager import PageManager


class NodeEditorPage(Page):
    name : str = "editor"

    def __init__(self, parent: int | str, menu_bar: int | str, page_manager: PageManager) -> None:
        self._node_editor_tag: int | str = dpg.generate_uuid()
        self._flow: Flow | None = None
        self._file_dialogs: list[int | str] = []
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

    # ── Node creation ──────────────────────────────────────────────────────────

    def _add_file_source_node(self, node: FileSource) -> None:
        """Create a File Source visual node with a file path input and browse button."""
        
        assert node is not None, "Node to add cannot be None"

        dialog_tag = dpg.generate_uuid()
        path_input_tag = dpg.generate_uuid()

        def on_file_selected(sender: int | str, app_data: dict) -> None:
            path = app_data.get("file_path_name", "")
            node.file_path = path
            dpg.set_value(path_input_tag, path)

        with dpg.file_dialog(
            label="Select Image or Video File",
            callback=on_file_selected,
            tag=dialog_tag,
            show=False,
            width=700,
            height=400,
        ):
            dpg.add_file_extension(".png",  color=(0, 255, 0, 255),   custom_text="PNG Image")
            dpg.add_file_extension(".jpg",  color=(255, 255, 0, 255), custom_text="JPEG Image")
            dpg.add_file_extension(".jpeg", color=(255, 255, 0, 255), custom_text="JPEG Image")
            dpg.add_file_extension(".mp4",  color=(0, 200, 255, 255), custom_text="MP4 Video")
            dpg.add_file_extension(".cr2",  color=(255, 128, 0, 255), custom_text="RAW Image")

        self._file_dialogs.append(dialog_tag)

        with dpg.node(label=node.display_name, parent=self._node_editor_tag):
            for i, param in enumerate(node.params):
                with dpg.node_attribute(label=param.name, attribute_type=dpg.mvNode_Attr_Static):
                    if i > 0:
                        dpg.add_spacer(height=2)
                    dpg.add_text(param.name)
                    if param.param_type == NodeParamType.FILE_PATH:
                        with dpg.group(horizontal=True):
                            dpg.add_input_text(
                                tag=path_input_tag,
                                default_value="",
                                width=200,
                                hint="Select a file…",
                                callback=lambda s, a: setattr(node, param.name, a),
                            )
                            dpg.add_button(
                                label="…",
                                callback=lambda: dpg.show_item(dialog_tag),
                            )
                    elif param.param_type == NodeParamType.INT:
                        dpg.add_input_int(
                            default_value=param.metadata.get("default", 0),
                            width=100,
                            callback=lambda s, a: setattr(node, param.name, a),
                        )

            # Output ports
            if node.outputs:
                for i, port in enumerate(node.outputs):
                    with dpg.node_attribute(label=port.name, attribute_type=dpg.mvNode_Attr_Output):
                        if i == 0:
                            dpg.add_spacer(height=6)
                        dpg.add_text(", ".join(t.value for t in port.emits))

    # ── Link callbacks ─────────────────────────────────────────────────────────

    def _link(self, sender, app_data) -> None:
        dpg.add_node_link(app_data[0], app_data[1], parent=sender)

    def _delink(self, sender, app_data) -> None:
        dpg.delete_item(app_data)

    # ── Clear ──────────────────────────────────────────────────────────────────

    def _clear_nodes(self) -> None:
        children = dpg.get_item_children(self._node_editor_tag, 1)
        if children:
            for child in children:
                dpg.delete_item(child)
        for dialog_tag in self._file_dialogs:
            if dpg.does_item_exist(dialog_tag):
                dpg.delete_item(dialog_tag)
        self._file_dialogs.clear()
        if self._flow is not None:
            for node in list(self._flow.nodes):
                self._flow.remove_node(node)

    # ── Button / menu callbacks ────────────────────────────────────────────────

    def _on_add_node(self, sender=None) -> None:
        node = FileSource()
        if self._flow is not None:
            self._flow.add_node(node)
        self._add_file_source_node(node)

    def _on_clear_nodes(self, sender=None) -> None:
        self._clear_nodes()

    def _on_exit_clicked(self, sender=None) -> None:
        self._clear_nodes()
        self._page_manager.activate(self._page_manager.start_page)

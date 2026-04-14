from __future__ import annotations

import importlib
import logging
from typing import TYPE_CHECKING, Callable

import dearpygui.dearpygui as dpg
from typing_extensions import override

from core.flow import Flow
from core.node_base import NodeBase
from core.node_registry import NodeEntry, NodeRegistry
from ui._types import DpgTag
from ui.dpg_node_builder import DpgNodeBuilder
from ui.dpg_node_list_builder import DpgNodeListBuilder
from ui.page import Page

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ui.dpg_themes import DpgThemes
    from ui.page_manager import PageManager


class NodeEditorPage(Page):
    name: str = "editor"

    def __init__(
        self,
        parent: DpgTag,
        menu_bar: DpgTag,
        page_manager: PageManager,
        registry: NodeRegistry,
        themes: DpgThemes,
    ) -> None:
        self._node_editor_tag: DpgTag = dpg.generate_uuid()
        self._canvas_tag:      DpgTag = dpg.generate_uuid()
        self._flow:     Flow | None    = None
        self._registry: NodeRegistry    = registry
        self._node_builder: DpgNodeBuilder = DpgNodeBuilder(self._node_editor_tag, themes)

        # Node tracking for delete / context-menu support
        self._node_map:        dict[DpgTag, NodeBase]       = {}
        self._node_dialog_map: dict[DpgTag, DpgTag | None]  = {}
        self._ctx_target:      tuple[DpgTag, NodeBase] | None = None
        self._ctx_links:       list[DpgTag]                 = []

        # Context-menu window tags (windows populated in _build_ui)
        self._node_ctx_tag: DpgTag = dpg.generate_uuid()
        self._link_ctx_tag: DpgTag = dpg.generate_uuid()
        super().__init__(parent=parent, menu_bar=menu_bar, page_manager=page_manager, themes=themes)

    def set_flow(self, flow: Flow) -> None:
        self._flow = flow

    # ── UI construction ────────────────────────────────────────────────────────

    @override
    def _build_ui(self) -> None:
        self._build_ctx_menu(self._node_ctx_tag, "Delete Node", self._on_ctx_delete_node)
        self._build_ctx_menu(self._link_ctx_tag, "Delete Connection(s)", self._delete_selected_links)

        with dpg.handler_registry():
            dpg.add_mouse_click_handler(button=dpg.mvMouseButton_Right, callback=self._on_right_click)
            dpg.add_mouse_click_handler(button=dpg.mvMouseButton_Left,  callback=self._on_left_click)

        dpg.add_spacer(height=20)
        with dpg.group(horizontal=True):
            DpgNodeListBuilder(self._registry)
            with dpg.group():
                with dpg.group(horizontal=True):
                    dpg.add_button(label="Clear All", callback=self._clear_nodes)

                with dpg.child_window(
                    tag=self._canvas_tag,
                    drop_callback=self._on_node_dropped,
                    payload_type=DpgNodeListBuilder.PAYLOAD_TYPE,
                    width=-1,
                    height=-1,
                    border=False):
                    dpg.add_node_editor(
                        tag=self._node_editor_tag,
                        callback=self._link,
                        delink_callback=self._delink,
                        width=-1,
                        height=-1)

    @staticmethod
    def _build_ctx_menu(tag: DpgTag, item_label: str, callback: Callable[..., None]) -> None:
        with dpg.window(
            tag=tag,
            show=False,
            no_title_bar=True,
            autosize=True,
            no_scrollbar=True,
            no_move=True,
            no_resize=True,
            no_collapse=True,
            min_size=(10, 10),
        ):
            dpg.add_menu_item(label=item_label, callback=callback)

    # ── Node creation ──────────────────────────────────────────────────────────

    def _on_node_dropped(self, sender: DpgTag, app_data: NodeEntry) -> None:
        module = importlib.import_module(app_data.module)
        cls = getattr(module, app_data.class_name)
        node: NodeBase = cls()
        logger.debug("Adding node '%s'", node.display_name)

        if self._flow is not None:
            self._flow.add_node(node)

        node_tag = self._add_visual_node(node)
        mouse_pos  = dpg.get_mouse_pos(local=True)
        canvas_pos = dpg.get_item_pos(self._canvas_tag)
        dpg.set_item_pos(node_tag, [
            mouse_pos[0] - canvas_pos[0],
            mouse_pos[1] - canvas_pos[1],
        ])

    def _add_visual_node(self, node: NodeBase) -> DpgTag:
        node_tag, dialog_tag = self._node_builder.build(node)
        self._node_map[node_tag] = node
        self._node_dialog_map[node_tag] = dialog_tag
        return node_tag

    # ── Right-click / context menus ────────────────────────────────────────────

    def _on_right_click(self) -> None:
        """Show the appropriate context menu on right-click inside the editor."""
        if not self._active:
            return

        for tag, node in self._node_map.items():
            if dpg.does_item_exist(tag) and dpg.get_item_state(tag).get("hovered", False):
                self._ctx_target = (tag, node)
                self._hide_ctx_menus()
                dpg.set_item_pos(self._node_ctx_tag, dpg.get_mouse_pos())
                dpg.configure_item(self._node_ctx_tag, show=True)
                return

        self._ctx_links = dpg.get_selected_links(self._node_editor_tag)
        if not self._ctx_links:
            return
        self._hide_ctx_menus()
        dpg.set_item_pos(self._link_ctx_tag, dpg.get_mouse_pos())
        dpg.configure_item(self._link_ctx_tag, show=True)

    def _on_left_click(self) -> None:
        """Dismiss context menus when clicking outside them."""
        if not self._active:
            return
        for tag in (self._node_ctx_tag, self._link_ctx_tag):
            if dpg.does_item_exist(tag) and not dpg.get_item_state(tag).get("hovered", False):
                dpg.configure_item(tag, show=False)

    def _hide_ctx_menus(self) -> None:
        dpg.configure_item(self._node_ctx_tag, show=False)
        dpg.configure_item(self._link_ctx_tag, show=False)

    def _on_ctx_delete_node(self) -> None:
        dpg.configure_item(self._node_ctx_tag, show=False)
        if self._ctx_target is not None:
            self._delete_node(*self._ctx_target)
            self._ctx_target = None

    def _delete_node(self, node_tag: DpgTag, node: NodeBase) -> None:
        """Remove a node and all its connected links from the canvas and flow."""
        attr_tags = set(dpg.get_item_children(node_tag, 1) or [])

        # Links live in slot 0 of the node editor; scan only those.
        for link_tag in list(dpg.get_item_children(self._node_editor_tag, 0) or []):
            try:
                conf = dpg.get_item_configuration(link_tag)
            except SystemError:
                # Link may have been deleted mid-iteration (e.g. by DPG auto-cleanup).
                logger.debug("Skipped link %s while deleting node", link_tag, exc_info=True)
                continue
            if conf.get("attr_1") in attr_tags or conf.get("attr_2") in attr_tags:
                dpg.delete_item(link_tag)

        dialog_tag = self._node_dialog_map.pop(node_tag, None)
        if dialog_tag is not None and dpg.does_item_exist(dialog_tag):
            dpg.delete_item(dialog_tag)

        self._node_map.pop(node_tag, None)
        if dpg.does_item_exist(node_tag):
            dpg.delete_item(node_tag)
        logger.debug("Deleted node '%s'", node.display_name)

        if self._flow is not None:
            self._flow.remove_node(node)

    def _delete_selected_links(self) -> None:
        """Delete the links that were selected when the context menu was opened."""
        dpg.configure_item(self._link_ctx_tag, show=False)
        for link in self._ctx_links:
            if dpg.does_item_exist(link):
                dpg.delete_item(link)
        self._ctx_links = []

    # ── Link callbacks ─────────────────────────────────────────────────────────

    def _link(self, sender: DpgTag, app_data: tuple[DpgTag, DpgTag]) -> None:
        link_tag = dpg.add_node_link(app_data[0], app_data[1], parent=sender)
        self._themes.apply_to_link(link_tag)

    def _delink(self, sender: DpgTag, app_data: DpgTag) -> None:
        dpg.delete_item(app_data)

    # ── Clear ──────────────────────────────────────────────────────────────────

    def _clear_nodes(self, *_: object) -> None:
        for node_tag, node in list(self._node_map.items()):
            self._delete_node(node_tag, node)

        self._ctx_target = None
        self._ctx_links = []

    # ── Menu ───────────────────────────────────────────────────────────────────

    @override
    def _install_menus(self) -> None:
        menu_tag = dpg.generate_uuid()
        label = f"Node Editor [{self._flow.name}]" if self._flow is not None else "Node Editor"
        with dpg.menu(label=label, parent=self._menu_bar, tag=menu_tag):
            dpg.add_menu_item(label="Clear All", callback=self._clear_nodes)
            dpg.add_separator()
            dpg.add_menu_item(label="Exit", callback=self._on_exit_clicked)
        self._menu_tags.append(menu_tag)

    # ── Button / menu callbacks ────────────────────────────────────────────────

    def _on_exit_clicked(self, sender: DpgTag | None = None) -> None:
        logger.info("Exiting node editor")
        self._clear_nodes()
        self._page_manager.activate(self._page_manager.start_page)

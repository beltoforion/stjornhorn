from __future__ import annotations

import importlib
import logging
from typing import TYPE_CHECKING

import dearpygui.dearpygui as dpg

from core.flow import Flow
from core.node_base import NodeBase, NodeParamType
from core.node_registry import NodeEntry, NodeRegistry
from ui.node_editor_theme import NodeEditorTheme
from ui.page import Page

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ui.page_manager import PageManager

_PALETTE_WIDTH = 200


class NodeEditorPage(Page):
    name: str = "editor"

    def __init__(
        self,
        parent: int | str,
        menu_bar: int | str,
        page_manager: PageManager,
        registry: NodeRegistry,
    ) -> None:
        self._node_editor_tag: int | str = dpg.generate_uuid()
        self._canvas_tag:      int | str = dpg.generate_uuid()
        self._flow:     Flow | None          = None
        self._theme:    NodeEditorTheme | None = None   # created in _build_ui
        self._registry: NodeRegistry         = registry
        self._palette_items: list[tuple[int | str, str]] = []
        self._file_dialogs:  list[int | str]             = []
        # Node tracking for delete / context-menu support
        self._node_map:        dict[int | str, NodeBase]         = {}
        self._node_dialog_map: dict[int | str, int | str | None] = {}
        self._ctx_target:      tuple[int | str, NodeBase] | None = None
        self._ctx_links:       list[int | str]                   = []
        # Context-menu window tags (created in _build_ui)
        self._node_ctx_tag:    int | str = dpg.generate_uuid()
        self._link_ctx_tag:    int | str = dpg.generate_uuid()
        self._handler_reg_tag: int | str = dpg.generate_uuid()
        super().__init__(parent=parent, menu_bar=menu_bar, page_manager=page_manager)

    def set_flow(self, flow: Flow) -> None:
        self._flow = flow

    def _build_ui(self) -> None:
        # Theme must be created after dpg.create_context(); owned here for the
        # lifetime of this page.
        self._theme = NodeEditorTheme()

        # ── Context menus (floating windows, shown/hidden on demand) ───────────
        with dpg.window(
            tag=self._node_ctx_tag,
            show=False,
            no_title_bar=True,
            autosize=True,
            no_scrollbar=True,
            no_move=True,
            no_resize=True,
            no_collapse=True,
            min_size=(10, 10),
        ):
            dpg.add_menu_item(label="Delete Node", callback=self._on_ctx_delete_node)

        with dpg.window(
            tag=self._link_ctx_tag,
            show=False,
            no_title_bar=True,
            autosize=True,
            no_scrollbar=True,
            no_move=True,
            no_resize=True,
            no_collapse=True,
            min_size=(10, 10),
        ):
            dpg.add_menu_item(label="Delete Connection(s)", callback=self._delete_selected_links)

        # ── Global mouse handlers ──────────────────────────────────────────────
        with dpg.handler_registry(tag=self._handler_reg_tag):
            dpg.add_mouse_click_handler(
                button=dpg.mvMouseButton_Right,
                callback=self._on_right_click,
            )
            dpg.add_mouse_click_handler(
                button=dpg.mvMouseButton_Left,
                callback=self._on_left_click,
            )

        dpg.add_spacer(height=20)
        with dpg.group(horizontal=True):
            # ── Left: node palette ─────────────────────────────────────────────
            with dpg.child_window(width=_PALETTE_WIDTH, height=-1, border=True):
                self._build_palette()

            # ── Right: node editor canvas ──────────────────────────────────────
            with dpg.group():
                with dpg.group(horizontal=True):
                    dpg.add_button(label="Clear All", callback=self._on_clear_nodes)
                with dpg.child_window(
                    tag=self._canvas_tag,
                    drop_callback=self._on_node_dropped,
                    payload_type="NODE_PALETTE",
                    width=-1,
                    height=-1,
                    border=False,
                ):
                    dpg.add_node_editor(
                        tag=self._node_editor_tag,
                        callback=self._link,
                        delink_callback=self._delink,
                        width=-1,
                        height=-1,
                    )

    # ── Palette ────────────────────────────────────────────────────────────────

    def _build_palette(self) -> None:
        dpg.add_input_text(
            hint="Search…",
            width=-1,
            callback=self._on_palette_search,
        )
        dpg.add_separator()

        categorized = self._registry.nodes_by_category()

        for category in ("Sources", "Filters", "Sinks"):
            entries = categorized.get(category, [])
            with dpg.collapsing_header(label=f"{category}  ({len(entries)})", default_open=True):
                if not entries:
                    dpg.add_text("(none)", color=(120, 120, 120, 255))
                for entry in entries:
                    tag = dpg.generate_uuid()
                    dpg.add_button(label=entry.display_name, tag=tag, width=-1)
                    with dpg.drag_payload(
                        parent=tag,
                        drag_data=entry,
                        payload_type="NODE_PALETTE",
                    ):
                        dpg.add_text(f"+ {entry.display_name}")
                    self._palette_items.append((tag, entry.display_name.lower()))

    def _on_palette_search(self, sender: int | str, value: str) -> None:
        query = value.strip().lower()
        for tag, text in self._palette_items:
            dpg.configure_item(tag, show=(not query or query in text))

    def _on_node_dropped(self, sender: int | str, app_data) -> None:
        entry: NodeEntry = app_data
        module = importlib.import_module(entry.module)
        cls = getattr(module, entry.class_name)
        node: NodeBase = cls()
        logger.debug("Adding node '%s'", node.display_name)
        if self._flow is not None:
            self._flow.add_node(node)
        node_tag = self._add_visual_node(node)
        # get_mouse_pos(local=True) is relative to the main window origin.
        # Subtract the canvas child_window's offset to get node editor coordinates.
        mouse_pos  = dpg.get_mouse_pos(local=True)
        canvas_pos = dpg.get_item_pos(self._canvas_tag)
        dpg.set_item_pos(node_tag, [
            mouse_pos[0] - canvas_pos[0],
            mouse_pos[1] - canvas_pos[1],
        ])

    # ── Node creation ──────────────────────────────────────────────────────────

    def _add_visual_node(self, node: NodeBase) -> int | str:
        """Create a visual node driven by node.params, node.inputs, and node.outputs."""
        assert node is not None
        assert self._theme is not None

        # Only create a file dialog if this node has FILE_PATH params
        has_file_param = any(p.param_type == NodeParamType.FILE_PATH for p in node.params)
        dialog_tag: int | str | None = None
        path_input_tags: dict[str, int | str] = {}

        if has_file_param:
            dialog_tag = dpg.generate_uuid()

            def on_file_selected(sender: int | str, app_data: dict) -> None:
                path = app_data.get("file_path_name", "")
                active_param = dpg.get_item_user_data(sender)
                if active_param and active_param in path_input_tags:
                    dpg.set_value(path_input_tags[active_param], path)
                setattr(node, active_param or "file_path", path)

            with dpg.file_dialog(
                label="Select File",
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

        with dpg.node(label=node.display_name, parent=self._node_editor_tag) as node_tag:
            self._theme.apply_to_node(node_tag, node)

            # Static parameter attributes
            for i, param in enumerate(node.params):
                with dpg.node_attribute(label=param.name, attribute_type=dpg.mvNode_Attr_Static):
                    if i > 0:
                        dpg.add_spacer(height=2)
                    dpg.add_text(param.name)

                    if param.param_type == NodeParamType.FILE_PATH:
                        input_tag = dpg.generate_uuid()
                        path_input_tags[param.name] = input_tag
                        with dpg.group(horizontal=True):
                            dpg.add_input_text(
                                tag=input_tag,
                                default_value=str(param.metadata.get("default", "")),
                                width=200,
                                hint="Select a file…",
                                callback=lambda s, a, p=param: setattr(node, p.name, a),
                            )
                            dpg.add_button(
                                label="…",
                                user_data=param.name,
                                callback=lambda s, a, p=param.name: (
                                    dpg.configure_item(dialog_tag, user_data=p),
                                    dpg.show_item(dialog_tag),
                                ),
                            )

                    elif param.param_type == NodeParamType.INT:
                        dpg.add_input_int(
                            default_value=int(param.metadata.get("default", 0)),
                            width=100,
                            callback=lambda s, a, p=param: setattr(node, p.name, a),
                        )

            # Input ports
            for port in node.inputs:
                with dpg.node_attribute(label=port.name, attribute_type=dpg.mvNode_Attr_Input) as attr_tag:
                    self._theme.apply_to_input_pin(attr_tag)
                    dpg.add_text(", ".join(t.value for t in port.accepted_types))

            # Output ports
            for i, port in enumerate(node.outputs):
                with dpg.node_attribute(label=port.name, attribute_type=dpg.mvNode_Attr_Output) as attr_tag:
                    self._theme.apply_to_output_pin(attr_tag)
                    if i == 0:
                        dpg.add_spacer(height=6)
                    dpg.add_text(", ".join(t.value for t in port.emits))

        # Register node for context-menu / delete tracking
        self._node_map[node_tag] = node
        self._node_dialog_map[node_tag] = dialog_tag

        return node_tag

    # ── Right-click / context menus ────────────────────────────────────────────

    def _on_right_click(self) -> None:
        """Show the appropriate context menu on right-click inside the editor."""
        if not self._active:
            return

        # If a node is hovered, offer node deletion
        for tag in self._node_map:
            if dpg.does_item_exist(tag) and dpg.get_item_state(tag).get("hovered", False):
                self._ctx_target = (tag, self._node_map[tag])
                self._hide_ctx_menus()
                dpg.set_item_pos(self._node_ctx_tag, dpg.get_mouse_pos())
                dpg.configure_item(self._node_ctx_tag, show=True)
                return

        # No node hovered — snapshot selected links now (selection may clear later)
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

    def _delete_node(self, node_tag: int | str, node: NodeBase) -> None:
        """Remove a node and all its connected links from the canvas and flow."""
        # Collect attribute tags so we can find connected links
        attr_tags = set(dpg.get_item_children(node_tag, 1) or [])

        # Delete any links that reference this node's attributes
        for child in list(dpg.get_item_children(self._node_editor_tag, 1) or []):
            if child in self._node_map:
                continue  # it's a node, not a link
            try:
                conf = dpg.get_item_configuration(child)
                if conf.get("attr_1") in attr_tags or conf.get("attr_2") in attr_tags:
                    dpg.delete_item(child)
            except Exception:
                logger.debug("Skipped child %s while deleting node links", child, exc_info=True)

        # Clean up file dialog owned by this node (if any)
        dialog_tag = self._node_dialog_map.pop(node_tag, None)
        if dialog_tag is not None and dpg.does_item_exist(dialog_tag):
            dpg.delete_item(dialog_tag)
            try:
                self._file_dialogs.remove(dialog_tag)
            except ValueError:
                pass

        # Delete the visual node
        self._node_map.pop(node_tag, None)
        if dpg.does_item_exist(node_tag):
            dpg.delete_item(node_tag)
        logger.debug("Deleted node '%s'", node.display_name)

        # Remove from flow model
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

    def _link(self, sender, app_data) -> None:
        link_tag = dpg.add_node_link(app_data[0], app_data[1], parent=sender)
        if self._theme is not None:
            self._theme.apply_to_link(link_tag)

    def _delink(self, sender, app_data) -> None:
        dpg.delete_item(app_data)

    # ── Clear ──────────────────────────────────────────────────────────────────

    def _clear_nodes(self) -> None:
        # Links live in slot 0, nodes in slot 1.  Delete links first so that
        # node-attribute references are never dangling when a node is removed.
        for link in dpg.get_item_children(self._node_editor_tag, 0) or []:
            if dpg.does_item_exist(link):
                dpg.delete_item(link)

        for node in dpg.get_item_children(self._node_editor_tag, 1) or []:
            if dpg.does_item_exist(node):
                dpg.delete_item(node)

        for dialog_tag in self._file_dialogs:
            if dpg.does_item_exist(dialog_tag):
                dpg.delete_item(dialog_tag)

        self._file_dialogs.clear()
        self._node_map.clear()
        self._node_dialog_map.clear()
        self._ctx_target = None
        self._ctx_links = []

        if self._flow is not None:
            for node in list(self._flow.nodes):
                self._flow.remove_node(node)

    # ── Menu ───────────────────────────────────────────────────────────────────

    def _install_menus(self) -> None:
        menu_tag = dpg.generate_uuid()
        with dpg.menu(label="Node Editor", parent=self._menu_bar, tag=menu_tag):
            dpg.add_menu_item(label="Clear All", callback=self._on_clear_nodes)
            dpg.add_separator()
            dpg.add_menu_item(label="Exit", callback=self._on_exit_clicked)
        self._menu_tags.append(menu_tag)

    # ── Button / menu callbacks ────────────────────────────────────────────────

    def _on_clear_nodes(self, sender=None) -> None:
        self._clear_nodes()

    def _on_exit_clicked(self, sender=None) -> None:
        logger.info("Exiting node editor")
        self._clear_nodes()
        self._page_manager.activate(self._page_manager.start_page)

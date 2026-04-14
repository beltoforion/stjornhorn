from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Callable

import dearpygui.dearpygui as dpg

from constants import INPUT_DIR, OUTPUT_DIR
from core.flow import Flow
from core.node_base import NodeBase, NodeParam, NodeParamType
from core.node_registry import NodeEntry, NodeRegistry
from ui._types import DpgTag
from ui.node_editor_theme import NodeEditorTheme
from ui.node_palette_widget import NodePaletteWidget
from ui.page import Page

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from core.port import InputPort, OutputPort
    from ui.page_manager import PageManager


# ── File-dialog extension registrations ────────────────────────────────────────
# Each entry is (extension, rgba, label).

_SAVE_EXTS: tuple[tuple[str, tuple[int, int, int, int], str], ...] = (
    (".png",  (0,   255, 0,   255), "PNG Image"),
    (".jpg",  (255, 255, 0,   255), "JPEG Image"),
    (".jpeg", (255, 255, 0,   255), "JPEG Image"),
)

_OPEN_EXTS: tuple[tuple[str, tuple[int, int, int, int], str], ...] = (
    (".*",    (200, 200, 200, 255), "All Files"),
    (".png",  (0,   255, 0,   255), "PNG Image"),
    (".jpg",  (255, 255, 0,   255), "JPEG Image"),
    (".jpeg", (255, 255, 0,   255), "JPEG Image"),
    (".mp4",  (0,   200, 255, 255), "MP4 Video"),
    (".cr2",  (255, 128, 0,   255), "RAW Image"),
)


class NodeEditorPage(Page):
    name: str = "editor"

    def __init__(
        self,
        parent: DpgTag,
        menu_bar: DpgTag,
        page_manager: PageManager,
        registry: NodeRegistry,
    ) -> None:
        self._node_editor_tag: DpgTag = dpg.generate_uuid()
        self._canvas_tag:      DpgTag = dpg.generate_uuid()
        self._flow:     Flow | None    = None
        self._theme:    NodeEditorTheme = NodeEditorTheme()
        self._registry: NodeRegistry    = registry

        # Node tracking for delete / context-menu support
        self._node_map:        dict[DpgTag, NodeBase]       = {}
        self._node_dialog_map: dict[DpgTag, DpgTag | None]  = {}
        self._ctx_target:      tuple[DpgTag, NodeBase] | None = None
        self._ctx_links:       list[DpgTag]                 = []

        # Context-menu window tags (windows populated in _build_ui)
        self._node_ctx_tag: DpgTag = dpg.generate_uuid()
        self._link_ctx_tag: DpgTag = dpg.generate_uuid()
        super().__init__(parent=parent, menu_bar=menu_bar, page_manager=page_manager)

    def set_flow(self, flow: Flow) -> None:
        self._flow = flow

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self._build_ctx_menu(self._node_ctx_tag, "Delete Node", self._on_ctx_delete_node)
        self._build_ctx_menu(self._link_ctx_tag, "Delete Connection(s)", self._delete_selected_links)

        with dpg.handler_registry():
            dpg.add_mouse_click_handler(button=dpg.mvMouseButton_Right, callback=self._on_right_click)
            dpg.add_mouse_click_handler(button=dpg.mvMouseButton_Left,  callback=self._on_left_click)

        self._build_canvas()

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

    def _build_canvas(self) -> None:
        dpg.add_spacer(height=20)
        with dpg.group(horizontal=True):
            NodePaletteWidget(self._registry)
            with dpg.group():
                with dpg.group(horizontal=True):
                    dpg.add_button(label="Clear All", callback=self._clear_nodes)

                with dpg.child_window(
                    tag=self._canvas_tag,
                    drop_callback=self._on_node_dropped,
                    payload_type=NodePaletteWidget.PAYLOAD_TYPE,
                    width=-1,
                    height=-1,
                    border=False):
                    dpg.add_node_editor(
                        tag=self._node_editor_tag,
                        callback=self._link,
                        delink_callback=self._delink,
                        width=-1,
                        height=-1)

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
        """Create a visual node driven by node.params, node.inputs, and node.outputs."""
        dialog_tag, path_input_tags = self._build_file_dialog(node)

        with dpg.node(label=node.display_name, parent=self._node_editor_tag) as node_tag:
            self._theme.apply_to_node(node_tag, node)

            for i, param in enumerate(node.params):
                with dpg.node_attribute(label=param.name, attribute_type=dpg.mvNode_Attr_Static):
                    if i > 0:
                        dpg.add_spacer(height=2)
                    dpg.add_text(param.name)

                    if param.param_type == NodeParamType.FILE_PATH:
                        assert dialog_tag is not None
                        self._build_file_path_param(node, param, path_input_tags, dialog_tag)
                    elif param.param_type == NodeParamType.INT:
                        self._build_int_param(node, param)

            for port in node.inputs:
                self._build_input_port(port)

            for i, port in enumerate(node.outputs):
                self._build_output_port(port, is_first=(i == 0))

        self._node_map[node_tag] = node
        self._node_dialog_map[node_tag] = dialog_tag
        return node_tag


    def _build_file_dialog(self, node: NodeBase) -> tuple[DpgTag | None, dict[str, DpgTag]]:
        """Build the node's file dialog, if any. Returns (dialog_tag, path_input_tags)."""
        file_params = [p for p in node.params if p.param_type == NodeParamType.FILE_PATH]
        if not file_params:
            return None, {}

        dialog_tag: DpgTag = dpg.generate_uuid()
        path_input_tags: dict[str, DpgTag] = {}
        is_save = any(p.metadata.get("mode") == "save" for p in file_params)

        def on_file_selected(sender: DpgTag, app_data: dict) -> None:
            path = app_data.get("file_path_name", "")
            active_param = dpg.get_item_user_data(sender)
            assert active_param in path_input_tags, f"Unknown file-dialog target: {active_param!r}"
            dpg.set_value(path_input_tags[active_param], path)
            setattr(node, active_param, path)

        extensions = _SAVE_EXTS if is_save else _OPEN_EXTS
        with dpg.file_dialog(
            label="Save File As" if is_save else "Select File",
            callback=on_file_selected,
            tag=dialog_tag,
            show=False,
            width=700,
            height=400,
        ):
            for ext, color, label in extensions:
                dpg.add_file_extension(ext, color=color, custom_text=label)

        return dialog_tag, path_input_tags

    def _build_file_path_param(
        self,
        node: NodeBase,
        param: NodeParam,
        path_input_tags: dict[str, DpgTag],
        dialog_tag: DpgTag) -> None:
        input_tag: DpgTag = dpg.generate_uuid()
        path_input_tags[param.name] = input_tag
        is_save = param.metadata.get("mode") == "save"

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
                callback=self._make_browse_callback(param.name, input_tag, dialog_tag, is_save),
            )

    @staticmethod
    def _build_int_param(node: NodeBase, param: NodeParam) -> None:
        dpg.add_input_int(
            default_value=int(param.metadata.get("default", 0)),
            width=100,
            callback=lambda s, a, p=param: setattr(node, p.name, a))

    def _build_input_port(self, port: InputPort) -> None:
        with dpg.node_attribute(label=port.name, attribute_type=dpg.mvNode_Attr_Input) as attr_tag:
            self._theme.apply_to_input_pin(attr_tag)
            dpg.add_text(", ".join(t.value for t in port.accepted_types))

    def _build_output_port(self, port: OutputPort, *, is_first: bool) -> None:
        with dpg.node_attribute(label=port.name, attribute_type=dpg.mvNode_Attr_Output) as attr_tag:
            self._theme.apply_to_output_pin(attr_tag)
            if is_first:
                dpg.add_spacer(height=6)
            dpg.add_text(", ".join(t.value for t in port.emits))

    @staticmethod
    def _make_browse_callback(
        param_name: str,
        input_tag: DpgTag,
        dialog_tag: DpgTag,
        is_save: bool,
    ) -> Callable[..., None]:
        def _browse(sender: DpgTag | None = None, app_data: object = None) -> None:
            current = dpg.get_value(input_tag) or ""
            folder = Path(current).parent.resolve()
            fallback = OUTPUT_DIR if is_save else INPUT_DIR
            initial = str(folder) if folder.is_dir() else str(fallback)
            logger.debug("File dialog initial path: %s", initial)
            dpg.configure_item(dialog_tag, user_data=param_name, default_path=initial)
            dpg.show_item(dialog_tag)
        return _browse

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
        self._theme.apply_to_link(link_tag)

    def _delink(self, sender: DpgTag, app_data: DpgTag) -> None:
        dpg.delete_item(app_data)

    # ── Clear ──────────────────────────────────────────────────────────────────

    def _clear_nodes(self, *_: object) -> None:
        for node_tag, node in list(self._node_map.items()):
            self._delete_node(node_tag, node)

        self._ctx_target = None
        self._ctx_links = []

    # ── Menu ───────────────────────────────────────────────────────────────────

    def _install_menus(self) -> None:
        menu_tag = dpg.generate_uuid()
        with dpg.menu(label="Node Editor", parent=self._menu_bar, tag=menu_tag):
            dpg.add_menu_item(label="Clear All", callback=self._clear_nodes)
            dpg.add_separator()
            dpg.add_menu_item(label="Exit", callback=self._on_exit_clicked)
        self._menu_tags.append(menu_tag)

    # ── Button / menu callbacks ────────────────────────────────────────────────

    def _on_exit_clicked(self, sender: DpgTag | None = None) -> None:
        logger.info("Exiting node editor")
        self._clear_nodes()
        self._page_manager.activate(self._page_manager.start_page)

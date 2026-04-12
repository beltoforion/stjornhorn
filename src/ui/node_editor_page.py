from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

import dearpygui.dearpygui as dpg

from core.flow import Flow
from core.node_base import NodeBase, NodeParamType, SourceNodeBase, SinkNodeBase
from core.node_registry import NodeEntry, NodeRegistry
from ui.page import Page

if TYPE_CHECKING:
    from ui.page_manager import PageManager

_PALETTE_WIDTH = 200

# ── Node header colours (title, hovered, selected) ────────────────────────────
_COL_SOURCE = ((30, 100, 180, 255), ( 50, 120, 200, 255), ( 60, 130, 210, 255))
_COL_FILTER = ((30, 140,  60, 255), ( 40, 160,  70, 255), ( 50, 170,  80, 255))
_COL_SINK   = ((180, 100,  20, 255), (200, 120,  30, 255), (210, 130,  40, 255))

# ── Pin colours (normal, hovered) ─────────────────────────────────────────────
_COL_PIN_INPUT  = ((210, 210, 210, 255), (255, 255, 255, 255))
_COL_PIN_OUTPUT = ((220, 180,   0, 255), (240, 200,  30, 255))


def _make_node_theme(title, hovered, selected) -> int | str:
    with dpg.theme() as theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvNodeCol_TitleBar,         title,    category=dpg.mvThemeCat_Nodes)
            dpg.add_theme_color(dpg.mvNodeCol_TitleBarHovered,  hovered,  category=dpg.mvThemeCat_Nodes)
            dpg.add_theme_color(dpg.mvNodeCol_TitleBarSelected, selected, category=dpg.mvThemeCat_Nodes)
    return theme


def _make_pin_theme(normal, hovered) -> int | str:
    with dpg.theme() as theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvNodeCol_Pin,        normal,  category=dpg.mvThemeCat_Nodes)
            dpg.add_theme_color(dpg.mvNodeCol_PinHovered, hovered, category=dpg.mvThemeCat_Nodes)
    return theme


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
        self._flow: Flow | None = None
        self._file_dialogs: list[int | str] = []
        self._registry: NodeRegistry = registry
        self._palette_items: list[tuple[int | str, str]] = []
        # Themes are created in _build_ui (DPG context must exist first)
        self._theme_source:      int | str | None = None
        self._theme_filter:      int | str | None = None
        self._theme_sink:        int | str | None = None
        self._theme_pin_input:   int | str | None = None
        self._theme_pin_output:  int | str | None = None
        super().__init__(parent=parent, menu_bar=menu_bar, page_manager=page_manager)

    def set_flow(self, flow: Flow) -> None:
        self._flow = flow

    def _build_ui(self) -> None:
        # Create shared themes once; reused for every node added later
        self._theme_source     = _make_node_theme(*_COL_SOURCE)
        self._theme_filter     = _make_node_theme(*_COL_FILTER)
        self._theme_sink       = _make_node_theme(*_COL_SINK)
        self._theme_pin_input  = _make_pin_theme(*_COL_PIN_INPUT)
        self._theme_pin_output = _make_pin_theme(*_COL_PIN_OUTPUT)

        dpg.add_spacer(height=20)
        with dpg.group(horizontal=True):
            # ── Left: node palette ─────────────────────────────────────────────
            with dpg.child_window(width=_PALETTE_WIDTH, height=-1, border=True):
                self._build_palette()

            # ── Right: node editor canvas ──────────────────────────────────────
            with dpg.group():
                with dpg.group(horizontal=True):
                    dpg.add_button(label="Clear All", callback=self._on_clear_nodes)
                dpg.add_node_editor(
                    tag=self._node_editor_tag,
                    callback=self._link,
                    delink_callback=self._delink,
                    drop_callback=self._on_node_dropped,
                    payload_type="NODE_PALETTE",
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
        if self._flow is not None:
            self._flow.add_node(node)
        node_tag = self._add_visual_node(node)
        # Position the new node at the drop location
        mouse_pos  = dpg.get_mouse_pos(local=False)
        editor_min = dpg.get_item_rect_min(self._node_editor_tag)
        dpg.set_item_pos(node_tag, [
            mouse_pos[0] - editor_min[0],
            mouse_pos[1] - editor_min[1],
        ])

    # ── Node creation ──────────────────────────────────────────────────────────

    def _add_visual_node(self, node: NodeBase) -> int | str:
        """Create a visual node driven by node.params, node.inputs, and node.outputs."""
        assert node is not None

        # Pick the right header theme for this node's category
        if isinstance(node, SourceNodeBase):
            node_theme = self._theme_source
        elif isinstance(node, SinkNodeBase):
            node_theme = self._theme_sink
        else:
            node_theme = self._theme_filter

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
            dpg.bind_item_theme(node_tag, node_theme)

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
                    dpg.bind_item_theme(attr_tag, self._theme_pin_input)
                    dpg.add_text(", ".join(t.value for t in port.accepted_types))

            # Output ports
            for i, port in enumerate(node.outputs):
                with dpg.node_attribute(label=port.name, attribute_type=dpg.mvNode_Attr_Output) as attr_tag:
                    dpg.bind_item_theme(attr_tag, self._theme_pin_output)
                    if i == 0:
                        dpg.add_spacer(height=6)
                    dpg.add_text(", ".join(t.value for t in port.emits))

        return node_tag

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
        self._clear_nodes()
        self._page_manager.activate(self._page_manager.start_page)

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

import dearpygui.dearpygui as dpg

from core.flow import Flow
from core.node_base import NodeBase, NodeParamType, SourceNodeBase
from core.node_registry import NodeEntry, NodeRegistry
from ui.page import Page

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
        self._flow: Flow | None = None
        self._file_dialogs: list[int | str] = []
        self._registry: NodeRegistry = registry
        # (item_tag, lowercase search text) — populated in _build_palette
        self._palette_items: list[tuple[int | str, str]] = []
        super().__init__(parent=parent, menu_bar=menu_bar, page_manager=page_manager)

    def set_flow(self, flow: Flow) -> None:
        self._flow = flow

    def _build_ui(self) -> None:
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
            label = f"{category}  ({len(entries)})"
            with dpg.collapsing_header(label=label, default_open=True):
                if not entries:
                    dpg.add_text("(none)", color=(120, 120, 120, 255))
                for entry in entries:
                    tag = dpg.generate_uuid()
                    dpg.add_button(
                        label=entry.display_name,
                        tag=tag,
                        width=-1,
                        callback=self._on_palette_add,
                        user_data=entry,
                    )
                    self._palette_items.append((tag, entry.display_name.lower()))

    def _on_palette_search(self, sender: int | str, value: str) -> None:
        query = value.strip().lower()
        for tag, text in self._palette_items:
            dpg.configure_item(tag, show=(not query or query in text))

    def _on_palette_add(self, sender: int | str, app_data, entry: NodeEntry) -> None:
        module = importlib.import_module(entry.module)
        cls = getattr(module, entry.class_name)
        node: NodeBase = cls()
        if self._flow is not None:
            self._flow.add_node(node)
        self._add_visual_node(node)

    # ── Node creation ──────────────────────────────────────────────────────────

    def _add_visual_node(self, node: NodeBase) -> None:
        """Create a visual node driven by node.params and node.outputs."""
        assert node is not None

        # Only create a file dialog if this node has FILE_PATH params
        has_file_param = any(
            p.param_type == NodeParamType.FILE_PATH for p in node.params
        )
        dialog_tag: int | str | None = None
        path_input_tags: dict[str, int | str] = {}  # param_name -> input_tag

        if has_file_param:
            dialog_tag = dpg.generate_uuid()

            def on_file_selected(sender: int | str, app_data: dict) -> None:
                path = app_data.get("file_path_name", "")
                # Update whichever path input triggered the open (stored in user_data)
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
            if isinstance(node, SourceNodeBase):
                with dpg.theme() as source_theme:
                    with dpg.theme_component(dpg.mvAll):
                        dpg.add_theme_color(dpg.mvNodeCol_TitleBar,         (0, 128, 0, 255), category=dpg.mvThemeCat_Nodes)
                        dpg.add_theme_color(dpg.mvNodeCol_TitleBarHovered,  (0, 160, 0, 255), category=dpg.mvThemeCat_Nodes)
                        dpg.add_theme_color(dpg.mvNodeCol_TitleBarSelected, (0, 180, 0, 255), category=dpg.mvThemeCat_Nodes)
                dpg.bind_item_theme(node_tag, source_theme)

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

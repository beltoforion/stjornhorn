from __future__ import annotations

import importlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Literal

import dearpygui.dearpygui as dpg
from typing_extensions import override

from constants import FLOW_DIR
from core.flow import Flow
from core.node_base import NodeBase
from core.node_registry import NodeEntry, NodeRegistry
from ui._types import DpgTag
from ui.dpg_flow_viewer_panel import DpgFlowViewerPanel
from ui.dpg_node_builder import DpgNodeBuilder
from ui.dpg_node_list_builder import DpgNodeListBuilder
from ui.flow_file_dialog import FLOW_FILE_EXTENSION, make_open_flow_dialog
from ui.page import Page

_FLOW_FORMAT_VERSION = 1
_PortKind = Literal["input", "output"]

_SAVE_OK_COLOR   = ( 90, 200, 100, 255)
_SAVE_FAIL_COLOR = (220,  80,  80, 255)

# Fixed height of the viewer panel at the bottom of the editor page.
_VIEWER_HEIGHT: int = 300

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
        self._save_status_tag: DpgTag = dpg.generate_uuid()
        self._flow:     Flow | None    = None
        self._registry: NodeRegistry    = registry
        self._node_builder: DpgNodeBuilder = DpgNodeBuilder(self._node_editor_tag, themes)
        # Palette widget and bottom viewer are created in _build_ui.
        self._palette:  DpgNodeListBuilder | None = None
        self._viewer:   DpgFlowViewerPanel  | None = None
        self._palette_visible: bool = True
        # Last polled node-editor selection, used to avoid rebuilding the
        # viewer panel on every frame.
        self._last_selected_nodes: tuple[DpgTag, ...] = ()

        # Node tracking for delete / context-menu / save support
        self._node_map:        dict[DpgTag, NodeBase]       = {}
        self._node_dialog_map: dict[DpgTag, DpgTag | None]  = {}
        self._attr_to_port:    dict[DpgTag, tuple[NodeBase, _PortKind, int]] = {}
        self._ctx_target:      tuple[DpgTag, NodeBase] | None = None
        self._ctx_links:       list[DpgTag]                 = []

        # Context-menu window tags (windows populated in _build_ui)
        self._node_ctx_tag:    DpgTag = dpg.generate_uuid()
        self._link_ctx_tag:    DpgTag = dpg.generate_uuid()
        # The Node Editor menu is re-created on every activation, but we
        # keep a stable tag so the label can be refreshed in-place when
        # the flow is swapped out (e.g. after an Open).
        self._editor_menu_tag: DpgTag = dpg.generate_uuid()
        self._open_dialog_tag: DpgTag = dpg.generate_uuid()
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

        dpg.add_spacer(height=8)
        with dpg.group(horizontal=True):
            dpg.add_button(label="Palette",   callback=self._toggle_palette)
            dpg.add_button(label="Run",       callback=self._run_flow)
            dpg.add_button(label="Save",      callback=self._save_flow)
            dpg.add_button(label="Open",      callback=self._on_open_flow)
            dpg.add_button(label="Clear All", callback=self._clear_nodes)
            dpg.add_spacer(width=16)
            # Status readout updated by _save_flow / load_flow / _run_flow.
            # Empty until the first action attempt.
            dpg.add_text("", tag=self._save_status_tag)

        # Palette (left) + canvas (right), sized to leave room for the
        # viewer panel below. Negative height means "fill minus N".
        with dpg.group(horizontal=True, height=-_VIEWER_HEIGHT - 8):
            self._palette = DpgNodeListBuilder(self._registry)
            with dpg.child_window(
                tag=self._canvas_tag,
                drop_callback=self._on_node_dropped,
                payload_type=DpgNodeListBuilder.PAYLOAD_TYPE,
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

        # Bottom: viewer panel. Shows every IoDataType.IMAGE output of
        # the currently-selected node. Populated via selection polling.
        self._viewer = DpgFlowViewerPanel(parent=self._content_tag, height=_VIEWER_HEIGHT)

        # Persistent file dialog used by the Open button. Shared factory
        # so StartPage and NodeEditorPage stay in sync on filter / layout.
        make_open_flow_dialog(self._open_dialog_tag, self._on_flow_file_selected)

        # Start polling the node-editor selection so the viewer follows it.
        self._schedule_selection_poll()

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
        self._index_node_attrs(node_tag, node)
        return node_tag

    def _index_node_attrs(self, node_tag: DpgTag, node: NodeBase) -> None:
        """Record the mapping from each port's DPG attribute tag to
        ``(node, 'input'|'output', port_index)``.

        DpgNodeBuilder creates node_attribute children in this order:
        one per NodeParam (static), then one per input port, then one
        per output port. We rely on that order to resolve attribute
        tags back to ports at save time.
        """
        children = dpg.get_item_children(node_tag, 1) or []
        offset = len(node.params)
        for i in range(len(node.inputs)):
            self._attr_to_port[children[offset + i]] = (node, "input", i)
        offset += len(node.inputs)
        for i in range(len(node.outputs)):
            self._attr_to_port[children[offset + i]] = (node, "output", i)

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

        for attr_tag in attr_tags:
            self._attr_to_port.pop(attr_tag, None)

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
        """Create the visual link and mirror the connection into self._flow."""
        endpoints = self._resolve_endpoints(app_data[0], app_data[1])
        if endpoints is None:
            return
        src, dst = endpoints
        if self._flow is not None:
            try:
                self._flow.connect(src[0], src[2], dst[0], dst[2])
            except TypeError:
                logger.warning("Rejected incompatible connection", exc_info=True)
                return
        link_tag = dpg.add_node_link(app_data[0], app_data[1], parent=sender)
        self._themes.apply_to_link(link_tag)

    def _delink(self, sender: DpgTag, app_data: DpgTag) -> None:
        """Delete the visual link and tear down the matching Flow connection."""
        link_tag = app_data
        endpoints = self._link_endpoints(link_tag)
        if endpoints is not None and self._flow is not None:
            src, dst = endpoints
            try:
                self._flow.disconnect(src[0], src[2], dst[0], dst[2])
            except Exception:
                logger.debug("Flow.disconnect failed on delink", exc_info=True)
        if dpg.does_item_exist(link_tag):
            dpg.delete_item(link_tag)

    def _resolve_endpoints(
        self,
        attr_a: DpgTag,
        attr_b: DpgTag,
    ) -> tuple[tuple[NodeBase, _PortKind, int], tuple[NodeBase, _PortKind, int]] | None:
        """Translate a pair of node_attribute tags to (output_endpoint, input_endpoint)
        using self._attr_to_port. Returns None when the pair is invalid
        (unknown attr, same-kind pair, etc.)."""
        a = self._attr_to_port.get(attr_a)
        b = self._attr_to_port.get(attr_b)
        if a is None or b is None:
            return None
        if a[1] == "output" and b[1] == "input":
            return a, b
        if a[1] == "input" and b[1] == "output":
            return b, a
        return None

    def _link_endpoints(
        self,
        link_tag: DpgTag,
    ) -> tuple[tuple[NodeBase, _PortKind, int], tuple[NodeBase, _PortKind, int]] | None:
        """Return (output, input) endpoints for an existing node_link."""
        try:
            conf = dpg.get_item_configuration(link_tag)
        except SystemError:
            return None
        return self._resolve_endpoints(conf.get("attr_1"), conf.get("attr_2"))

    # ── Clear ──────────────────────────────────────────────────────────────────

    def _clear_nodes(self, *_: object) -> None:
        for node_tag, node in list(self._node_map.items()):
            self._delete_node(node_tag, node)

        self._ctx_target = None
        self._ctx_links = []
        # Wipe any stale save-status message so the readout matches the canvas.
        self._set_save_status("", _SAVE_OK_COLOR)

    # ── Menu ───────────────────────────────────────────────────────────────────

    @override
    def _install_menus(self) -> None:
        with dpg.menu(label=self._menu_label(), parent=self._menu_bar, tag=self._editor_menu_tag):
            dpg.add_menu_item(label="Save",      callback=self._save_flow)
            dpg.add_menu_item(label="Open",      callback=self._on_open_flow)
            dpg.add_menu_item(label="Clear All", callback=self._clear_nodes)
            dpg.add_separator()
            dpg.add_menu_item(label="Back",      callback=self._on_back_clicked)
        self._menu_tags.append(self._editor_menu_tag)

    def _menu_label(self) -> str:
        return f"Node Editor [{self._flow.name}]" if self._flow is not None else "Node Editor"

    def _refresh_menu_label(self) -> None:
        """Re-apply the menu label after self._flow has changed."""
        if dpg.does_item_exist(self._editor_menu_tag):
            dpg.configure_item(self._editor_menu_tag, label=self._menu_label())

    # ── Save ───────────────────────────────────────────────────────────────────

    def _save_flow(self, *_: object) -> None:
        if self._flow is None:
            logger.warning("Save requested but no flow is active")
            self._set_save_status("No flow to save", _SAVE_FAIL_COLOR)
            return
        data = self._serialize_flow(self._flow)
        try:
            FLOW_DIR.mkdir(parents=True, exist_ok=True)
            path = FLOW_DIR / f"{self._flow.name}{FLOW_FILE_EXTENSION}"
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError as err:
            logger.exception("Failed to save flow '%s'", self._flow.name)
            self._set_save_status(f"Save failed ({err.strerror or err.__class__.__name__})",
                                  _SAVE_FAIL_COLOR)
            return
        logger.info("Saved flow to %s", path)
        self._set_save_status(
            f"Saved to {self._display_path(path)} at {datetime.now().strftime('%H:%M:%S')}",
            _SAVE_OK_COLOR,
        )

    def _set_save_status(self, message: str, color: tuple[int, int, int, int]) -> None:
        """Update the Save-status readout below the button row."""
        if not dpg.does_item_exist(self._save_status_tag):
            return
        dpg.set_value(self._save_status_tag, message)
        dpg.configure_item(self._save_status_tag, color=color)

    @staticmethod
    def _display_path(path: Path) -> str:
        """Return ``path`` relative to the current working directory when
        possible, otherwise the absolute path. Keeps the status line short."""
        try:
            return str(path.relative_to(Path.cwd()))
        except ValueError:
            return str(path)

    def _serialize_flow(self, flow: Flow) -> dict:
        """Return a JSON-compatible dict snapshot of the current editor state."""
        nodes_in_order = list(self._node_map.items())  # insertion order == creation order
        node_ids: dict[int, int] = {id(node): idx for idx, (_, node) in enumerate(nodes_in_order)}

        nodes_out = [self._node_to_dict(i, tag, node) for i, (tag, node) in enumerate(nodes_in_order)]
        connections_out = self._connections_to_list(node_ids)

        return {
            "version":     _FLOW_FORMAT_VERSION,
            "name":        flow.name,
            "nodes":       nodes_out,
            "connections": connections_out,
        }

    def _node_to_dict(self, node_id: int, node_tag: DpgTag, node: NodeBase) -> dict:
        pos = dpg.get_item_pos(node_tag)
        params = {p.name: _jsonable(getattr(node, p.name, None)) for p in node.params}
        return {
            "id":       node_id,
            "module":   type(node).__module__,
            "class":    type(node).__name__,
            "position": [float(pos[0]), float(pos[1])],
            "params":   params,
        }

    def _connections_to_list(self, node_ids: dict[int, int]) -> list[dict]:
        """Derive connections from the DPG node_editor's visible links.

        The editor authoritatively owns link state today (Flow.connect is
        not yet wired to the UI), so we walk slot 0 of the editor to
        recover them.
        """
        result: list[dict] = []
        for link_tag in dpg.get_item_children(self._node_editor_tag, 0) or []:
            try:
                conf = dpg.get_item_configuration(link_tag)
            except SystemError:
                logger.debug("Skipped link %s during save", link_tag, exc_info=True)
                continue
            endpoint_a = self._attr_to_port.get(conf.get("attr_1"))
            endpoint_b = self._attr_to_port.get(conf.get("attr_2"))
            if endpoint_a is None or endpoint_b is None:
                continue
            # Normalise to (output, input) order. DPG doesn't guarantee
            # which of attr_1 / attr_2 is the source.
            if endpoint_a[1] == "output" and endpoint_b[1] == "input":
                src, dst = endpoint_a, endpoint_b
            elif endpoint_a[1] == "input" and endpoint_b[1] == "output":
                src, dst = endpoint_b, endpoint_a
            else:
                logger.debug("Skipping link with same-kind endpoints: %s", link_tag)
                continue
            result.append({
                "src_node":   node_ids[id(src[0])],
                "src_output": src[2],
                "dst_node":   node_ids[id(dst[0])],
                "dst_input":  dst[2],
            })
        return result

    # ── Open ───────────────────────────────────────────────────────────────────

    def _on_open_flow(self, *_: object) -> None:
        """Show the Open-Flow file dialog, seeded at FLOW_DIR."""
        FLOW_DIR.mkdir(parents=True, exist_ok=True)
        dpg.configure_item(self._open_dialog_tag, default_path=str(FLOW_DIR))
        dpg.show_item(self._open_dialog_tag)

    def _on_flow_file_selected(self, sender: DpgTag, app_data: dict) -> None:
        path_str = app_data.get("file_path_name", "")
        if not path_str:
            return
        self.load_flow(Path(path_str))

    def load_flow(self, path: Path) -> None:
        """Parse ``path`` as flow JSON and rebuild the editor to match."""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as err:
            logger.exception("Failed to read flow %s", path)
            self._set_save_status(f"Open failed ({err.__class__.__name__})", _SAVE_FAIL_COLOR)
            return

        version = data.get("version")
        if version != _FLOW_FORMAT_VERSION:
            logger.warning("Flow %s has unsupported version %r", path, version)
            self._set_save_status(f"Open failed (unsupported version {version!r})",
                                  _SAVE_FAIL_COLOR)
            return

        # Replace the current canvas and flow.
        self._clear_nodes()
        flow = Flow(name=data.get("name", path.stem))
        self.set_flow(flow)
        self._refresh_menu_label()

        # Materialise each node, remembering the JSON-id → (node_tag, NodeBase)
        # mapping so connections can be resolved below.
        id_to_node: dict[int, tuple[DpgTag, NodeBase]] = {}
        for entry in data.get("nodes", []):
            built = self._instantiate_node(entry)
            if built is None:
                continue
            node, position = built
            flow.add_node(node)
            node_tag = self._add_visual_node(node)
            dpg.set_item_pos(node_tag, list(position))
            id_to_node[entry["id"]] = (node_tag, node)

        # Restore connections as DPG links. Flow.connect is not yet wired
        # from the UI, so we intentionally mirror the save-side behaviour
        # and keep link state in DPG alone.
        for conn in data.get("connections", []):
            self._restore_connection(conn, id_to_node)

        logger.info("Loaded flow from %s", path)
        self._set_save_status(
            f"Loaded {self._display_path(path)} at {datetime.now().strftime('%H:%M:%S')}",
            _SAVE_OK_COLOR,
        )

    def _instantiate_node(self, entry: dict) -> tuple[NodeBase, tuple[float, float]] | None:
        """Construct a NodeBase from a serialized node entry.

        Returns None (and logs) if the module/class is unknown, so loading
        can proceed with the remaining nodes instead of failing the whole
        flow.
        """
        module_name = entry.get("module", "")
        class_name  = entry.get("class", "")
        try:
            module = importlib.import_module(module_name)
            cls    = getattr(module, class_name)
        except (ImportError, AttributeError):
            logger.exception("Cannot resolve node %s.%s", module_name, class_name)
            return None

        try:
            node: NodeBase = cls()
        except Exception:
            logger.exception("Failed to instantiate %s.%s", module_name, class_name)
            return None

        for name, value in (entry.get("params") or {}).items():
            try:
                setattr(node, name, value)
            except Exception:
                logger.warning("Ignoring param %s on %s.%s (%r)",
                               name, module_name, class_name, value)

        pos = entry.get("position") or [0.0, 0.0]
        return node, (float(pos[0]), float(pos[1]))

    def _restore_connection(
        self,
        conn: dict,
        id_to_node: dict[int, tuple[DpgTag, NodeBase]],
    ) -> None:
        src = id_to_node.get(conn.get("src_node"))
        dst = id_to_node.get(conn.get("dst_node"))
        if src is None or dst is None:
            logger.debug("Skipping connection with unknown endpoint: %s", conn)
            return
        src_tag, src_node = src
        dst_tag, dst_node = dst
        src_attrs = self._port_attrs(src_tag, src_node, "output")
        dst_attrs = self._port_attrs(dst_tag, dst_node, "input")
        try:
            src_idx = conn["src_output"]
            dst_idx = conn["dst_input"]
            src_attr = src_attrs[src_idx]
            dst_attr = dst_attrs[dst_idx]
        except (IndexError, KeyError):
            logger.warning("Skipping connection with out-of-range port index: %s", conn)
            return
        if self._flow is not None:
            try:
                self._flow.connect(src_node, src_idx, dst_node, dst_idx)
            except TypeError:
                logger.warning("Skipping incompatible connection: %s", conn, exc_info=True)
                return
        link_tag = dpg.add_node_link(src_attr, dst_attr, parent=self._node_editor_tag)
        self._themes.apply_to_link(link_tag)

    def _port_attrs(self, node_tag: DpgTag, node: NodeBase, kind: _PortKind) -> list[DpgTag]:
        """Return the ordered DPG attr tags for a node's input or output ports.

        Mirrors the ordering in _index_node_attrs: params, then inputs,
        then outputs.
        """
        children = dpg.get_item_children(node_tag, 1) or []
        params_len = len(node.params)
        inputs_len = len(node.inputs)
        if kind == "input":
            return list(children[params_len : params_len + inputs_len])
        return list(children[params_len + inputs_len : params_len + inputs_len + len(node.outputs)])

    # ── Run / viewer / palette ─────────────────────────────────────────────────

    def _run_flow(self, *_: object) -> None:
        """Execute the active flow once and refresh the viewer panel."""
        if self._flow is None:
            self._set_save_status("No flow to run", _SAVE_FAIL_COLOR)
            return
        try:
            self._flow.run()
        except Exception as err:
            logger.exception("Flow run failed")
            self._set_save_status(f"Run failed ({type(err).__name__})", _SAVE_FAIL_COLOR)
            return
        self._set_save_status(
            f"Ran at {datetime.now().strftime('%H:%M:%S')}",
            _SAVE_OK_COLOR,
        )
        if self._viewer is not None:
            self._viewer.refresh()

    def _toggle_palette(self, *_: object) -> None:
        if self._palette is None:
            return
        self._palette_visible = not self._palette_visible
        dpg.configure_item(self._palette.container_tag, show=self._palette_visible)

    def _schedule_selection_poll(self) -> None:
        """Arrange for :meth:`_poll_selection` to run on the next DPG frame."""
        dpg.set_frame_callback(dpg.get_frame_count() + 1, self._poll_selection)

    def _poll_selection(self) -> None:
        """Push the current node-editor selection into the viewer panel.

        Re-schedules itself every frame. Cheap: ``get_selected_nodes`` is a
        list lookup and we only touch the viewer on actual changes.
        """
        try:
            if self._active and dpg.does_item_exist(self._node_editor_tag):
                selected = tuple(dpg.get_selected_nodes(self._node_editor_tag) or ())
                if selected != self._last_selected_nodes:
                    self._last_selected_nodes = selected
                    if self._viewer is not None:
                        node = self._node_map.get(selected[0]) if selected else None
                        self._viewer.show(node)
        finally:
            self._schedule_selection_poll()

    # ── Button / menu callbacks ────────────────────────────────────────────────

    def _on_back_clicked(self, sender: DpgTag | None = None) -> None:
        logger.info("Returning to start page")
        self._clear_nodes()
        self._page_manager.activate(self._page_manager.start_page)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _jsonable(value: object) -> object:
    """Coerce ``value`` to a JSON-serialisable form (recursive for containers)."""
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    return value

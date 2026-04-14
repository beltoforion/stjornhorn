from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Callable

import dearpygui.dearpygui as dpg

from constants import INPUT_DIR, OUTPUT_DIR
from core.node_base import NodeBase, NodeParam, NodeParamType
from ui._types import DpgTag

if TYPE_CHECKING:
    from core.port import InputPort, OutputPort
    from ui.dpg_themes import DpgThemes

logger = logging.getLogger(__name__)


# ── File-dialog extension registrations ────────────────────────────────────────
# Each entry is (extension, rgba, label).

_SAVE_EXTS: tuple[tuple[str, tuple[int, int, int, int], str], ...] = (
    (".png",  (0,   255, 0,   255), "PNG Image"),
    (".jpg",  (255, 255, 0,   255), "JPEG Image")
)

_OPEN_EXTS: tuple[tuple[str, tuple[int, int, int, int], str], ...] = (
    (".*",    (200, 200, 200, 255), "All Files"),
    (".png",  (0,   255, 0,   255), "PNG Image"),
    (".jpg",  (255, 255, 0,   255), "JPEG Image"),
    (".jpeg", (255, 255, 0,   255), "JPEG Image"),
    (".mp4",  (0,   200, 255, 255), "MP4 Video"),
    (".cr2",  (255, 128, 0,   255), "RAW Image"),
)


class DpgNodeBuilder:
    """Builds the DearPyGUI widget tree for a single NodeBase on a node_editor.

    A builder is created once per NodeEditorPage and reused across node drops.
    Call :meth:`build` to materialise one node; it returns the node's DPG tag
    plus the optional file-dialog tag so the caller can track both for
    deletion.

    Adding a new ``NodeParamType``: write a ``_build_*_param`` method that
    takes a :class:`NodeParam` and register it in ``self._param_builders``.
    """

    def __init__(self, node_editor_tag: DpgTag, theme: DpgThemes) -> None:
        self._node_editor_tag: DpgTag = node_editor_tag
        self._theme: DpgThemes = theme

        # Per-build scratch state, reset at the start of build().
        self._current_node: NodeBase | None = None
        self._dialog_tag: DpgTag | None = None
        self._path_input_tags: dict[str, DpgTag] = {}

        # Dispatch table: NodeParamType -> method that renders a NodeParam row.
        self._param_builders: dict[NodeParamType, Callable[[NodeParam], None]] = {
            NodeParamType.FILE_PATH: self._build_file_path_param,
            NodeParamType.INT:       self._build_int_param,
        }

    # ── Public API ─────────────────────────────────────────────────────────────

    def build(self, node: NodeBase) -> tuple[DpgTag, DpgTag | None]:
        """Create the visual node. Returns ``(node_tag, dialog_tag_or_None)``."""
        self._current_node = node
        self._path_input_tags = {}
        self._dialog_tag = self._build_file_dialog(node)

        try:
            with dpg.node(label=node.display_name, parent=self._node_editor_tag) as node_tag:
                self._theme.apply_to_node(node_tag, node)

                for i, param in enumerate(node.params):
                    with dpg.node_attribute(label=param.name, attribute_type=dpg.mvNode_Attr_Static):
                        if i > 0:
                            dpg.add_spacer(height=2)
                        dpg.add_text(param.name)
                        self._build_param(param)

                for port in node.inputs:
                    self._build_input_port(port)

                for i, port in enumerate(node.outputs):
                    self._build_output_port(port, is_first=(i == 0))

            return node_tag, self._dialog_tag
        finally:
            self._current_node = None

    # ── Param dispatch ─────────────────────────────────────────────────────────

    def _build_param(self, param: NodeParam) -> None:
        builder = self._param_builders.get(param.param_type)
        if builder is None:
            logger.warning("No UI builder registered for param type %s", param.param_type)
            return
        builder(param)

    # ── Param builders ─────────────────────────────────────────────────────────

    def _build_file_path_param(self, param: NodeParam) -> None:
        assert self._dialog_tag is not None, "FILE_PATH param requires a file dialog"
        assert self._current_node is not None
        node = self._current_node

        input_tag: DpgTag = dpg.generate_uuid()
        self._path_input_tags[param.name] = input_tag
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
                callback=self._make_browse_callback(param.name, input_tag, self._dialog_tag, is_save),
            )

    def _build_int_param(self, param: NodeParam) -> None:
        assert self._current_node is not None
        node = self._current_node
        dpg.add_input_int(
            default_value=int(param.metadata.get("default", 0)),
            width=100,
            callback=lambda s, a, p=param: setattr(node, p.name, a),
        )

    # ── Ports ──────────────────────────────────────────────────────────────────

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

    # ── File dialog ────────────────────────────────────────────────────────────

    def _build_file_dialog(self, node: NodeBase) -> DpgTag | None:
        """Build the node's shared file dialog, if any FILE_PATH param exists."""
        file_params = [p for p in node.params if p.param_type == NodeParamType.FILE_PATH]
        if not file_params:
            return None

        dialog_tag: DpgTag = dpg.generate_uuid()
        is_save = any(p.metadata.get("mode") == "save" for p in file_params)
        # The FILE_PATH builder populates self._path_input_tags as it runs; the
        # dialog callback below closes over it so lookups see the final map.
        path_input_tags = self._path_input_tags

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

        return dialog_tag

    # ── Browse callback factory ────────────────────────────────────────────────

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

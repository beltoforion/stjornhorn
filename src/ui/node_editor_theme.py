from __future__ import annotations

import dearpygui.dearpygui as dpg

from core.node_base import NodeBase, SourceNodeBase, SinkNodeBase

# ── Colour palette ─────────────────────────────────────────────────────────────
# Each tuple is (normal, hovered, selected) unless noted.

_SOURCE_HEADER  = ((30, 100, 180, 255), ( 50, 120, 200, 255), ( 60, 130, 210, 255))
_FILTER_HEADER  = ((30, 140,  60, 255), ( 40, 160,  70, 255), ( 50, 170,  80, 255))
_SINK_HEADER    = ((180, 100, 20, 255), (200, 120,  30, 255), (210, 130,  40, 255))

_PIN_INPUT      = ((210, 210, 210, 255), (255, 255, 255, 255))   # (normal, hovered)
_PIN_OUTPUT     = ((220, 180,   0, 255), (240, 200,  30, 255))

_LINK           = ((180, 180, 180, 255), (255, 255, 255, 255), (220, 160, 0, 255))


class NodeEditorTheme:
    """Creates and owns all DPG theme objects used by the node editor.

    Must be instantiated after ``dpg.create_context()`` has been called,
    because DPG theme items are created immediately in ``__init__``.

    Usage::

        theme = NodeEditorTheme()
        theme.apply_to_node(node_tag, node)
        theme.apply_to_input_pin(attr_tag)
        theme.apply_to_output_pin(attr_tag)
        theme.apply_to_link(link_tag)
    """

    def __init__(self) -> None:
        self._source     = _make_node_header_theme(*_SOURCE_HEADER)
        self._filter     = _make_node_header_theme(*_FILTER_HEADER)
        self._sink       = _make_node_header_theme(*_SINK_HEADER)
        self._pin_input  = _make_pin_theme(*_PIN_INPUT)
        self._pin_output = _make_pin_theme(*_PIN_OUTPUT)
        self._link       = _make_link_theme(*_LINK)

    # ── Apply helpers ──────────────────────────────────────────────────────────

    def apply_to_node(self, tag: int | str, node: NodeBase) -> None:
        """Bind the correct header theme based on the node's category."""
        if isinstance(node, SourceNodeBase):
            theme = self._source
        elif isinstance(node, SinkNodeBase):
            theme = self._sink
        else:
            theme = self._filter
        dpg.bind_item_theme(tag, theme)

    def apply_to_input_pin(self, tag: int | str) -> None:
        dpg.bind_item_theme(tag, self._pin_input)

    def apply_to_output_pin(self, tag: int | str) -> None:
        dpg.bind_item_theme(tag, self._pin_output)

    def apply_to_link(self, tag: int | str) -> None:
        dpg.bind_item_theme(tag, self._link)


# ── Private factory functions ──────────────────────────────────────────────────

def _make_node_header_theme(title, hovered, selected) -> int | str:
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


def _make_link_theme(normal, hovered, selected) -> int | str:
    with dpg.theme() as theme:
        with dpg.theme_component(dpg.mvNodeLink):
            dpg.add_theme_color(dpg.mvNodeCol_Link,         normal,   category=dpg.mvThemeCat_Nodes)
            dpg.add_theme_color(dpg.mvNodeCol_LinkHovered,  hovered,  category=dpg.mvThemeCat_Nodes)
            dpg.add_theme_color(dpg.mvNodeCol_LinkSelected, selected, category=dpg.mvThemeCat_Nodes)
    return theme

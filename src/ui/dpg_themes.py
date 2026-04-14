from __future__ import annotations

import dearpygui.dearpygui as dpg

from core.node_base import NodeBase, SourceNodeBase, SinkNodeBase
from ui._types import DpgTag

# ── Colour palette ─────────────────────────────────────────────────────────────
# Each tuple is (normal, hovered, selected) unless noted.

_SOURCE_HEADER  = ((30, 100, 180, 255), ( 50, 120, 200, 255), ( 60, 130, 210, 255))
_FILTER_HEADER  = ((30, 140,  60, 255), ( 40, 160,  70, 255), ( 50, 170,  80, 255))
_SINK_HEADER    = ((180, 100, 20, 255), (200, 120,  30, 255), (210, 130,  40, 255))

_PIN_INPUT      = ((210, 210, 210, 255), (255, 255, 255, 255))   # (normal, hovered)
_PIN_OUTPUT     = ((220, 180,   0, 255), (240, 200,  30, 255))

_LINK           = ((180, 180, 180, 255), (255, 255, 255, 255), (220, 160, 0, 255))

_DISABLED_BUTTON_TEXT = (120, 120, 120, 255)
_DISABLED_BUTTON_FILL = ( 45,  45,  45, 255)


class DpgThemes:
    """Creates and owns all shared DPG theme objects used across the app.

    Must be instantiated after ``dpg.create_context()`` has been called,
    because DPG theme items are created immediately in ``__init__``.

    Usage::

        themes = DpgThemes()
        themes.apply_to_node(node_tag, node)
        themes.apply_to_input_pin(attr_tag)
        themes.apply_to_output_pin(attr_tag)
        themes.apply_to_link(link_tag)
        themes.apply_to_disabled_button(button_tag)
    """

    def __init__(self) -> None:
        self._source          = _make_node_header_theme(*_SOURCE_HEADER)
        self._filter          = _make_node_header_theme(*_FILTER_HEADER)
        self._sink            = _make_node_header_theme(*_SINK_HEADER)
        self._pin_input       = _make_pin_theme(*_PIN_INPUT)
        self._pin_output      = _make_pin_theme(*_PIN_OUTPUT)
        self._link            = _make_link_theme(*_LINK)
        self._disabled_button = _make_disabled_button_theme()

    # ── Apply helpers ──────────────────────────────────────────────────────────

    def apply_to_node(self, tag: DpgTag, node: NodeBase) -> None:
        """Bind the correct header theme based on the node's category."""
        if isinstance(node, SourceNodeBase):
            theme = self._source
        elif isinstance(node, SinkNodeBase):
            theme = self._sink
        else:
            theme = self._filter
        dpg.bind_item_theme(tag, theme)

    def apply_to_input_pin(self, tag: DpgTag) -> None:
        dpg.bind_item_theme(tag, self._pin_input)

    def apply_to_output_pin(self, tag: DpgTag) -> None:
        dpg.bind_item_theme(tag, self._pin_output)

    def apply_to_link(self, tag: DpgTag) -> None:
        dpg.bind_item_theme(tag, self._link)

    def apply_to_disabled_button(self, tag: DpgTag) -> None:
        """Grey the button out while it is ``enabled=False``.

        The colour overrides only apply in the disabled state; the enabled
        state continues to use DPG's default button theme.
        """
        dpg.bind_item_theme(tag, self._disabled_button)


# ── Private factory functions ──────────────────────────────────────────────────

def _make_node_header_theme(title, hovered, selected) -> DpgTag:
    with dpg.theme() as theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvNodeCol_TitleBar,         title,    category=dpg.mvThemeCat_Nodes)
            dpg.add_theme_color(dpg.mvNodeCol_TitleBarHovered,  hovered,  category=dpg.mvThemeCat_Nodes)
            dpg.add_theme_color(dpg.mvNodeCol_TitleBarSelected, selected, category=dpg.mvThemeCat_Nodes)
    return theme


def _make_pin_theme(normal, hovered) -> DpgTag:
    with dpg.theme() as theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvNodeCol_Pin,        normal,  category=dpg.mvThemeCat_Nodes)
            dpg.add_theme_color(dpg.mvNodeCol_PinHovered, hovered, category=dpg.mvThemeCat_Nodes)
    return theme


def _make_link_theme(normal, hovered, selected) -> DpgTag:
    with dpg.theme() as theme:
        with dpg.theme_component(dpg.mvNodeLink):
            dpg.add_theme_color(dpg.mvNodeCol_Link,         normal,   category=dpg.mvThemeCat_Nodes)
            dpg.add_theme_color(dpg.mvNodeCol_LinkHovered,  hovered,  category=dpg.mvThemeCat_Nodes)
            dpg.add_theme_color(dpg.mvNodeCol_LinkSelected, selected, category=dpg.mvThemeCat_Nodes)
    return theme


def _make_disabled_button_theme() -> DpgTag:
    with dpg.theme() as theme:
        with dpg.theme_component(dpg.mvButton, enabled_state=False):
            dpg.add_theme_color(dpg.mvThemeCol_Text,          _DISABLED_BUTTON_TEXT)
            dpg.add_theme_color(dpg.mvThemeCol_Button,        _DISABLED_BUTTON_FILL)
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, _DISABLED_BUTTON_FILL)
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  _DISABLED_BUTTON_FILL)
    return theme

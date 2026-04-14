from __future__ import annotations

from typing import TYPE_CHECKING

import dearpygui.dearpygui as dpg
from typing_extensions import override

from constants import APP_VERSION
from core.flow import DEFAULT_FLOW_NAME, Flow
from ui._types import DpgTag
from ui.page import Page

if TYPE_CHECKING:
    from ui.page_manager import PageManager


class StartPage(Page):
    name : str = "start"

    def __init__(self, parent: DpgTag, menu_bar: DpgTag, page_manager: PageManager) -> None:
        self._flow_name_input_tag: DpgTag = dpg.generate_uuid()
        super().__init__(parent=parent, menu_bar=menu_bar, page_manager=page_manager)

    @override
    def _build_ui(self) -> None:
        dpg.add_spacer(height=60)
        dpg.add_text("Image Inquest", indent=20)
        dpg.add_text(f"v{APP_VERSION}", indent=20, color=(120, 120, 120, 255))
        dpg.add_spacer(height=20)

        # Primary action: name the flow then create it. Enter in the input
        # also triggers creation, so a flow can be created without using
        # the mouse at all (optionally leaving the name blank to accept
        # the default).
        with dpg.group(horizontal=True, indent=20):
            dpg.add_input_text(
                tag=self._flow_name_input_tag,
                hint=DEFAULT_FLOW_NAME,
                width=220,
                on_enter=True,
                callback=self._on_create_flow,
            )
            dpg.add_button(label="Create", callback=self._on_create_flow)

        dpg.add_spacer(height=8)
        dpg.add_button(label="Load Flow", indent=20, callback=self._on_load_flow_clicked)

    @override
    def _install_menus(self) -> None:
        pass

    @override
    def _on_activated(self) -> None:
        # Focus the input so typing a name works immediately on (re-)entry.
        dpg.focus_item(self._flow_name_input_tag)

    # ── Callbacks ──────────────────────────────────────────────────────────────

    def _on_create_flow(self, sender: DpgTag | None = None, app_data: object = None) -> None:
        raw_name = dpg.get_value(self._flow_name_input_tag) or ""
        flow = Flow(name=raw_name)
        # Reflect the sanitized/defaulted name back into the input so the
        # user sees what will be saved.
        dpg.set_value(self._flow_name_input_tag, flow.name)
        self._page_manager.editor_page.set_flow(flow)
        self._page_manager.activate(self._page_manager.editor_page)

    def _on_load_flow_clicked(self, sender: DpgTag | None = None) -> None:
        pass  # TODO: implement flow loading (file dialog + deserialization)

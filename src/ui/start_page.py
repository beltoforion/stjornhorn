from __future__ import annotations

from typing import TYPE_CHECKING

import dearpygui.dearpygui as dpg
from typing_extensions import override

from constants import APP_VERSION
from core.flow import DEFAULT_FLOW_NAME, Flow, is_valid_flow_name
from ui._types import DpgTag
from ui.dpg_themes import DpgThemes
from ui.page import Page

if TYPE_CHECKING:
    from ui.page_manager import PageManager


class StartPage(Page):
    name : str = "start"

    def __init__(self, parent: DpgTag, menu_bar: DpgTag, page_manager: PageManager) -> None:
        self._flow_name_input_tag: DpgTag = dpg.generate_uuid()
        self._create_button_tag:   DpgTag = dpg.generate_uuid()
        self._themes:              DpgThemes = DpgThemes()
        super().__init__(parent=parent, menu_bar=menu_bar, page_manager=page_manager)

    @override
    def _build_ui(self) -> None:
        dpg.add_spacer(height=60)
        dpg.add_text("Image Inquest", indent=20)
        dpg.add_text(f"v{APP_VERSION}", indent=20, color=(120, 120, 120, 255))
        dpg.add_spacer(height=20)

        # Primary action: name the flow then create it. Enter in the input
        # also triggers creation. Create is disabled until the name is valid.
        with dpg.group(horizontal=True, indent=20):
            dpg.add_input_text(
                tag=self._flow_name_input_tag,
                hint=DEFAULT_FLOW_NAME,
                width=220,
                on_enter=True,
                callback=self._on_create_flow,
            )
            dpg.add_button(
                label="Create",
                tag=self._create_button_tag,
                enabled=False,
                callback=self._on_create_flow,
            )
            self._themes.apply_to_disabled_button(self._create_button_tag)

        # Live-validate the name on every keystroke so the Create button's
        # enabled state stays in sync with the input.
        with dpg.item_handler_registry() as handlers:
            dpg.add_item_edited_handler(callback=self._on_name_edited)
        dpg.bind_item_handler_registry(self._flow_name_input_tag, handlers)

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

    def _on_name_edited(self, sender: DpgTag, app_data: object) -> None:
        name = dpg.get_value(self._flow_name_input_tag) or ""
        dpg.configure_item(self._create_button_tag, enabled=is_valid_flow_name(name))

    def _on_create_flow(self, sender: DpgTag | None = None, app_data: object = None) -> None:
        name = dpg.get_value(self._flow_name_input_tag) or ""
        if not is_valid_flow_name(name):
            # Ignore Enter presses on an invalid/empty input; the Create
            # button is already disabled for the same reason.
            return
        flow = Flow(name=name)
        self._page_manager.editor_page.set_flow(flow)
        self._page_manager.activate(self._page_manager.editor_page)

    def _on_load_flow_clicked(self, sender: DpgTag | None = None) -> None:
        pass  # TODO: implement flow loading (file dialog + deserialization)

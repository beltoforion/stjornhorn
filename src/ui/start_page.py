import dearpygui.dearpygui as dpg

from ui.page import Page


class StartPage(Page):
    def __init__(self, parent: str, menu_bar: str, on_create_flow) -> None:
        self._on_create_flow = on_create_flow
        super().__init__(parent=parent, menu_bar=menu_bar)

    def _build(self) -> None:
        with dpg.child_window(tag=self._content_tag, parent=self._parent, border=False, show=False):
            dpg.add_spacer(height=60)
            dpg.add_text("Image Inquest", indent=20)
            dpg.add_spacer(height=20)
            dpg.add_button(label="New Flow", callback=self._on_new_flow, indent=20)

    def _install_menus(self) -> None:
        # Start page contributes no menus of its own.
        pass

    def _on_new_flow(self, sender) -> None:
        self._on_create_flow()

import dearpygui.dearpygui as dpg


class StartPage:
    def __init__(self, parent: str, on_create_flow) -> None:
        self._on_create_flow = on_create_flow
        self._tag = "start_page"
        self._build(parent)

    def show(self) -> None:
        dpg.show_item(self._tag)

    def hide(self) -> None:
        dpg.hide_item(self._tag)

    def _build(self, parent: str) -> None:
        with dpg.child_window(tag=self._tag, parent=parent, border=False):
            dpg.add_spacer(height=60)
            dpg.add_text("Image Inquest", indent=20)
            dpg.add_spacer(height=20)
            dpg.add_button(label="New Flow", callback=self._on_new_flow, indent=20)

    def _on_new_flow(self, sender) -> None:
        self._on_create_flow()

import os
import dearpygui.dearpygui as dpg

FLOW_EXT = ".niflow"
FLOW_DIR = "flows"


class StartPage:
    def __init__(self, parent: str, on_flow_selected) -> None:
        self._on_flow_selected = on_flow_selected
        self._selected_path: str = ""
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
            dpg.add_text("Select a node flow to open:", indent=20)
            dpg.add_spacer(height=10)

            flows = self._scan_flows()
            dpg.add_listbox(
                items=flows if flows else ["(no flows found)"],
                tag="flow_listbox",
                callback=self._on_list_select,
                num_items=8,
                width=500,
                indent=20,
            )
            dpg.add_spacer(height=10)

            with dpg.group(horizontal=True, indent=20):
                dpg.add_button(label="Browse...", callback=self._on_browse)
                dpg.add_button(label="Open", tag="open_button", callback=self._on_open, enabled=False)

        with dpg.file_dialog(
            label="Open Node Flow",
            directory_selector=False,
            show=False,
            callback=self._on_file_chosen,
            tag="file_dialog",
            width=600,
            height=400,
        ):
            dpg.add_file_extension(FLOW_EXT, color=(255, 220, 100, 255))
            dpg.add_file_extension(".*")

    def _scan_flows(self) -> list[str]:
        if not os.path.isdir(FLOW_DIR):
            return []
        return sorted(
            os.path.join(FLOW_DIR, f)
            for f in os.listdir(FLOW_DIR)
            if f.endswith(FLOW_EXT)
        )

    def _on_list_select(self, sender, app_data) -> None:
        flows = self._scan_flows()
        if app_data in flows:
            self._selected_path = app_data
            dpg.enable_item("open_button")

    def _on_browse(self, sender) -> None:
        dpg.show_item("file_dialog")

    def _on_file_chosen(self, sender, app_data) -> None:
        path = app_data.get("file_path_name", "")
        if path and os.path.isfile(path):
            self._on_flow_selected(path)

    def _on_open(self, sender) -> None:
        if self._selected_path:
            self._on_flow_selected(self._selected_path)

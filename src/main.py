import argparse

import dearpygui.dearpygui as dpg

from ui.main_window import MainWindow
from constants import APP_NAME, APP_VERSION, APP_WIDTH, APP_HEIGHT


class App:
    def __init__(self, width: int = APP_WIDTH, height: int = APP_HEIGHT) -> None:
        dpg.create_context()
        self._main_window = MainWindow()
        dpg.create_viewport(title=f"{APP_NAME} v{APP_VERSION}", width=width, height=height)

    def run(self) -> None:
        dpg.setup_dearpygui()
        dpg.show_viewport()
        dpg.set_primary_window(self._main_window.window_tag, True)
        dpg.start_dearpygui()
        dpg.destroy_context()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Image Inquest Application")
    parser.add_argument("--width",  type=int, default=APP_WIDTH,  help="Viewport width")
    parser.add_argument("--height", type=int, default=APP_HEIGHT, help="Viewport height")
    args = parser.parse_args()
    App(width=args.width, height=args.height).run()

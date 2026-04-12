import dearpygui.dearpygui as dpg
import argparse

from ui.main_window import *
from constants import APP_NAME, APP_VERSION, APP_WIDTH, APP_HEIGHT

class App:
    def __init__(self):
        dpg.create_context()
        self._main_window = MainWindow()

        dpg.create_viewport(title=f"{APP_NAME} v{APP_VERSION}", width=APP_WIDTH, height=APP_HEIGHT)

    def run(self):
        dpg.setup_dearpygui()
        dpg.show_viewport()
        dpg.set_primary_window(self._main_window.window_tag, True)
        dpg.start_dearpygui()
        dpg.destroy_context()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Image Inquest Application")
    parser.add_argument("--width", type=int, default=APP_WIDTH, help="Width of the application window")
    parser.add_argument("--height", type=int, default=APP_HEIGHT, help="Height of the application window")
    args = parser.parse_args()
    
    APP_WIDTH = args.width
    APP_HEIGHT = args.height

    App().run()
import argparse
import logging

import dearpygui.dearpygui as dpg

from constants import APP_NAME, APP_VERSION, APP_WIDTH, APP_HEIGHT, USER_CONFIG_DIR
from log import setup_logging
from ui.main_window import MainWindow

logger = logging.getLogger(__name__)


class App:
    def __init__(self, width: int = APP_WIDTH, height: int = APP_HEIGHT) -> None:
        dpg.create_context()
        self._main_window = MainWindow()
        dpg.create_viewport(title=f"{APP_NAME} v{APP_VERSION}", width=width, height=height)

    def run(self) -> None:
        logger.info("Starting %s v%s", APP_NAME, APP_VERSION)
        dpg.setup_dearpygui()
        dpg.show_viewport()
        dpg.set_primary_window(self._main_window.window_tag, True)
        dpg.start_dearpygui()
        dpg.destroy_context()
        logger.info("Shutdown complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Image Inquest Application")
    parser.add_argument("--width",  type=int, default=APP_WIDTH,  help="Viewport width")
    parser.add_argument("--height", type=int, default=APP_HEIGHT, help="Viewport height")
    args = parser.parse_args()

    setup_logging(USER_CONFIG_DIR / "logs")
    App(width=args.width, height=args.height).run()

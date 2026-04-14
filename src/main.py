from __future__ import annotations

import argparse
import logging
import sys

from PySide6.QtWidgets import QApplication

from constants import APP_NAME, APP_VERSION, APP_WIDTH, APP_HEIGHT, USER_CONFIG_DIR
from log import setup_logging
from ui.main_window import MainWindow
from ui.theme import apply_dark_theme

logger = logging.getLogger(__name__)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Image Inquest Application")
    parser.add_argument("--width",  type=int, default=APP_WIDTH,  help="Initial window width")
    parser.add_argument("--height", type=int, default=APP_HEIGHT, help="Initial window height")
    args, qt_args = parser.parse_known_args(argv)

    setup_logging(USER_CONFIG_DIR / "logs")
    logger.info("Starting %s v%s", APP_NAME, APP_VERSION)

    # Forward any unrecognised flags to Qt (e.g. -style, -platform) along
    # with the program name so QApplication.arguments() behaves normally.
    app = QApplication([sys.argv[0], *qt_args])
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    apply_dark_theme(app)

    window = MainWindow()
    window.resize(args.width, args.height)
    window.show()

    rc = app.exec()
    logger.info("Shutdown complete (rc=%d)", rc)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCursor, QGuiApplication, QPixmap, QScreen
from PySide6.QtWidgets import QApplication, QSplashScreen

from constants import (
    APP_NAME,
    APP_VERSION,
    FLOW_DIR,
    SPLASH_DURATION_MS,
    SPLASH_IMAGE_PATH,
    USER_CONFIG_DIR,
)
from log import setup_logging
from ui.main_window import MainWindow
from ui.theme import apply_dark_theme

logger = logging.getLogger(__name__)


_FLOW_EXT = ".flowjs"


def _resolve_flow_arg(arg: str) -> Path | None:
    """Resolve a ``--flow`` CLI argument to an existing flow file.

    Tries, in order:
      1. the literal path,
      2. the literal path with ``.flowjs`` appended,
      3. ``FLOW_DIR / arg`` (for bare names like ``my_flow``),
      4. ``FLOW_DIR / arg.flowjs``.

    Returns the first existing file (resolved absolute), or ``None``.
    """
    def _with_ext(p: Path) -> Path:
        return p if p.suffix == _FLOW_EXT else Path(f"{p}{_FLOW_EXT}")

    p = Path(arg)
    candidates: list[Path] = [p, _with_ext(p)]
    # Treat plain names (no directory component, not absolute) as
    # references into FLOW_DIR so users can type "my_flow" or
    # "my_flow.flowjs" without the flow/ prefix.
    if not p.is_absolute() and p.parent == Path("."):
        candidates.append(FLOW_DIR / arg)
        candidates.append(_with_ext(FLOW_DIR / arg))

    for c in candidates:
        if c.is_file():
            return c.resolve()
    return None


def _target_screen() -> QScreen:
    """Return the screen the app should launch on.

    On multi-monitor setups we want the splash and the main window to
    appear on the same display. The window manager typically puts new
    windows on the screen under the cursor, so we mirror that choice.
    Falls back to the primary screen if no screen is under the cursor
    (e.g. headless / unusual setups).
    """
    screen = QGuiApplication.screenAt(QCursor.pos())
    return screen if screen is not None else QGuiApplication.primaryScreen()


def _make_splash(screen: QScreen) -> QSplashScreen | None:
    """Build the startup splash screen, or return ``None`` if the image
    is missing / unreadable. Never fatal — a missing splash should not
    prevent the app from launching.
    """
    if not SPLASH_IMAGE_PATH.exists():
        logger.debug("Splash image not found at %s", SPLASH_IMAGE_PATH)
        return None

    pixmap = QPixmap(str(SPLASH_IMAGE_PATH))
    if pixmap.isNull():
        logger.warning("Splash image could not be loaded: %s", SPLASH_IMAGE_PATH)
        return None

    # Passing the screen explicitly pins the splash to the same monitor
    # the main window will open on — otherwise Qt centers it on the
    # primary screen, which may differ from the WM's choice for the
    # main window.
    splash = QSplashScreen(screen, pixmap, Qt.WindowStaysOnTopHint)
    splash.setAttribute(Qt.WA_DeleteOnClose)
    return splash


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Image Inquest Application")
    parser.add_argument("--no-splash", action="store_true", help="Skip the startup splash screen")
    parser.add_argument(
        "--flow",
        metavar="FILE",
        help="Load a flow at startup and open it directly in the editor. "
             "Accepts a path to a .flowjs file or a bare flow name (looked up in flow/).",
    )
    args, qt_args = parser.parse_known_args(argv)

    setup_logging(USER_CONFIG_DIR / "logs")
    logger.info("Starting %s v%s", APP_NAME, APP_VERSION)

    initial_flow_path: Path | None = None
    if args.flow:
        initial_flow_path = _resolve_flow_arg(args.flow)
        if initial_flow_path is None:
            logger.warning("Flow not found: %r", args.flow)

    # Forward any unrecognised flags to Qt (e.g. -style, -platform) along
    # with the program name so QApplication.arguments() behaves normally.
    app = QApplication([sys.argv[0], *qt_args])
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    apply_dark_theme(app)

    # Decide which monitor we're launching on before creating any
    # top-level widgets so splash and main window stay together.
    screen = _target_screen()

    # Show splash as early as possible so it's visible while the registry
    # scans and the main window is constructed.
    splash = None if args.no_splash else _make_splash(screen)
    if splash is not None:
        splash.show()
        app.processEvents()

    window = MainWindow(initial_flow_path=initial_flow_path)
    # Anchor the window on the chosen monitor before maximizing so the
    # window manager maximizes it there (not on the primary screen).
    geom = screen.availableGeometry()
    window.setGeometry(geom)

    if splash is not None:
        # Ensure the splash stays visible for at least SPLASH_DURATION_MS
        # even on fast machines, then hand off to the main window.
        def _reveal_main() -> None:
            window.showMaximized()
            splash.finish(window)

        QTimer.singleShot(SPLASH_DURATION_MS, _reveal_main)
    else:
        window.showMaximized()

    rc = app.exec()
    logger.info("Shutdown complete (rc=%d)", rc)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QPointF, QTimer
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QGuiApplication,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QScreen,
)
from PySide6.QtWidgets import QApplication, QSplashScreen

from constants import (
    APP_DISPLAY_NAME,
    APP_ICON_FALLBACK_PATH,
    APP_ICON_PATH,
    APP_NAME,
    APP_USER_MODEL_ID,
    APP_VERSION,
    FLOW_DIR,
    LOG_DIR,
    SPLASH_DURATION_MS,
    SPLASH_IMAGE_PATH,
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


def _set_windows_app_user_model_id() -> None:
    """On Windows, declare an explicit AppUserModelID for the process.

    Without this, a Python-hosted app inherits ``python.exe``'s identity
    and the taskbar shows the generic Python icon regardless of what we
    set via :meth:`QApplication.setWindowIcon`. Harmless (and silently
    skipped) on every other platform.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:
        logger.debug("Could not set AppUserModelID; taskbar icon may fall back to python.exe")


def _load_app_icon() -> QIcon:
    """Return the application icon, preferring the multi-resolution ``.ico``.

    Falls back to the ``.png`` if the ``.ico`` is missing or unreadable,
    and to an empty icon as a last resort so startup never fails over a
    missing asset.
    """
    for path in (APP_ICON_PATH, APP_ICON_FALLBACK_PATH):
        if path.exists():
            icon = QIcon(str(path))
            if not icon.isNull():
                return icon
            logger.warning("App icon at %s could not be loaded", path)
    logger.debug("No app icon found; using Qt default")
    return QIcon()


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


def _paint_splash_text(pixmap: QPixmap) -> QPixmap:
    """Overlay the app name and version onto the splash pixmap.

    Text is rendered at the bottom-left of the image with a dark
    outline so it stays legible on any background. Font sizes scale
    with pixmap height so the splash reads well whether the asset is
    small or large.
    """
    canvas = QPixmap(pixmap)
    painter = QPainter(canvas)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        w = canvas.width()
        h = canvas.height()
        margin = max(16, int(h * 0.04))
        title_px = max(24, int(h * 0.12))
        version_px = max(14, int(h * 0.055))

        title_font = QFont(painter.font().family())
        title_font.setPixelSize(title_px)
        title_font.setBold(True)
        title_font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 102)

        version_font = QFont(painter.font().family())
        version_font.setPixelSize(version_px)

        # Dark outline under a bright fill — keeps the text legible
        # regardless of what the underlying splash image looks like.
        outline_pen = QPen(QColor(0, 0, 0, 220))
        outline_pen.setWidthF(max(2.0, title_px * 0.08))
        outline_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        fill_color = QColor(245, 245, 245)

        def _stroked_text(x: float, baseline_y: float, font: QFont, text: str) -> None:
            path = QPainterPath()
            path.addText(QPointF(x, baseline_y), font, text)
            painter.setPen(outline_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(fill_color)
            painter.drawPath(path)

        # Baseline positions: version sits just above the bottom edge;
        # title sits above the version with a small gap. Both are
        # anchored to the left margin.
        version_baseline = h - margin
        # Using font metrics keeps the gap consistent across font sizes
        # and avoids relying on pixel-size heuristics.
        painter.setFont(version_font)
        version_ascent = painter.fontMetrics().ascent()
        title_baseline = version_baseline - version_ascent - int(title_px * 0.25)

        _stroked_text(margin, title_baseline, title_font, APP_DISPLAY_NAME)
        _stroked_text(margin, version_baseline, version_font, f"v{APP_VERSION}")

        # Best-effort: if the text would collide with the right edge
        # (very narrow splash), log it so the artwork or sizes can be
        # tweaked. Fall through either way — text will clip gracefully.
        painter.setFont(title_font)
        if painter.fontMetrics().horizontalAdvance(APP_DISPLAY_NAME) > w - 2 * margin:
            logger.debug("Splash title wider than available space — will clip")
    finally:
        painter.end()
    return canvas


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

    pixmap = _paint_splash_text(pixmap)

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

    setup_logging(LOG_DIR)
    logger.info("Starting %s v%s", APP_NAME, APP_VERSION)

    # Must happen before QApplication so Windows associates our icon with
    # the process's taskbar entry from the very first window.
    _set_windows_app_user_model_id()

    initial_flow_path: Path | None = None
    if args.flow:
        initial_flow_path = _resolve_flow_arg(args.flow)
        if initial_flow_path is None:
            logger.warning("Flow not found: %r", args.flow)

    # Forward any unrecognised flags to Qt (e.g. -style, -platform) along
    # with the program name so QApplication.arguments() behaves normally.
    app = QApplication([sys.argv[0], *qt_args])
    app.setApplicationName(APP_NAME)
    # Qt and some window managers auto-append applicationDisplayName to
    # every window caption, which would duplicate the prefix MainWindow
    # already renders (e.g. "Sparklehoof — flow — Sparklehoof"). We
    # build the full caption ourselves, so clear the display name.
    app.setApplicationDisplayName("")
    app.setApplicationVersion(APP_VERSION)
    app.setWindowIcon(_load_app_icon())
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

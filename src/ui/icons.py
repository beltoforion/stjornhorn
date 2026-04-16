"""Google Material Icons for the Sparklehoof UI.

Renders icons from the bundled ``MaterialIcons-Regular.ttf`` font as
:class:`QIcon` instances so they can be dropped into ``QAction``,
``QToolButton`` and any other Qt widget that accepts a ``QIcon``.

The font is loaded lazily on first use via :class:`QFontDatabase`. A
small name → codepoint table covers the icons used by the app today;
add new entries here as more icons are needed.
"""
from __future__ import annotations

from typing import Final

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QIcon,
    QIconEngine,
    QPainter,
    QPalette,
    QPixmap,
)
from PySide6.QtWidgets import QApplication

from constants import MATERIAL_ICONS_FONT_PATH


# Subset of Material Icon names → codepoints used by the app. Source:
# https://github.com/google/material-design-icons (MaterialIcons-Regular.codepoints)
# Keep this list intentionally small; extend as new icons are needed
# rather than shipping the full ~2200-entry table at runtime.
_CODEPOINTS: Final[dict[str, str]] = {
    "folder_open":  "e2c8",
    "home":         "e88a",
    "account_tree": "e97a",
    "play_arrow":   "e037",
    "save":         "e161",
    "save_as":      "eb60",
    "delete":       "e872",
    "zoom_out_map": "e56b",
    "fullscreen_exit": "e5d1",
}


_font_family: str | None = None


def _ensure_font_loaded() -> str:
    """Register the Material Icons font with Qt and return its family name.

    Cached after the first successful load. Requires a ``QApplication``
    to exist (font registration goes through the GUI subsystem).
    """
    global _font_family
    if _font_family is not None:
        return _font_family

    if QApplication.instance() is None:
        raise RuntimeError(
            "material_icon() requires a QApplication; create it before "
            "constructing icons."
        )

    font_id = QFontDatabase.addApplicationFont(str(MATERIAL_ICONS_FONT_PATH))
    if font_id == -1:
        raise RuntimeError(
            f"Failed to load Material Icons font from {MATERIAL_ICONS_FONT_PATH}"
        )
    families = QFontDatabase.applicationFontFamilies(font_id)
    if not families:
        raise RuntimeError(
            f"Material Icons font at {MATERIAL_ICONS_FONT_PATH} has no families"
        )
    _font_family = families[0]
    return _font_family


def _glyph_for(name: str) -> str:
    """Return the unicode glyph for a Material Icon ``name``."""
    try:
        codepoint = _CODEPOINTS[name]
    except KeyError as err:
        raise KeyError(
            f"Unknown Material Icon '{name}'. Add its codepoint to "
            f"ui.icons._CODEPOINTS."
        ) from err
    return chr(int(codepoint, 16))


class _MaterialIconEngine(QIconEngine):
    """QIconEngine that draws a Material Icons glyph at any requested size.

    Rendering a glyph each time (rather than caching a single QPixmap) keeps
    icons crisp at every toolbar size and lets the engine pick a sensible
    color for disabled/active states from the application palette.
    """

    def __init__(self, glyph: str, color: QColor | None) -> None:
        super().__init__()
        self._glyph = glyph
        self._color = QColor(color) if color is not None else None

    # Qt calls this for every paint at every size; keep it cheap.
    def paint(
        self,
        painter: QPainter,
        rect: QRect,
        mode: QIcon.Mode,
        state: QIcon.State,
    ) -> None:
        family = _ensure_font_loaded()
        # Material Icons render perfectly when the point size matches the
        # box height (the glyphs are designed on a square em).
        font = QFont(family)
        font.setPixelSize(max(1, rect.height()))
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setFont(font)
        painter.setPen(self._color_for(mode))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self._glyph)
        painter.restore()

    def pixmap(
        self,
        size: QSize,
        mode: QIcon.Mode,
        state: QIcon.State,
    ) -> QPixmap:
        pm = QPixmap(size)
        pm.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pm)
        try:
            self.paint(painter, QRect(QPoint(0, 0), size), mode, state)
        finally:
            painter.end()
        return pm

    def clone(self) -> QIconEngine:
        return _MaterialIconEngine(self._glyph, self._color)

    # ── Helpers ────────────────────────────────────────────────────────────

    def _color_for(self, mode: QIcon.Mode) -> QColor:
        if self._color is not None:
            base = QColor(self._color)
        else:
            app = QApplication.instance()
            if isinstance(app, QApplication):
                base = app.palette().color(QPalette.ColorRole.ButtonText)
            else:
                base = QColor(224, 224, 224)
        if mode == QIcon.Mode.Disabled:
            base.setAlpha(110)
        return base


def material_icon(name: str, *, color: QColor | None = None) -> QIcon:
    """Return a :class:`QIcon` rendering the Material Icon ``name``.

    ``color`` overrides the default (palette button-text) color. The icon
    scales crisply to any size Qt requests.
    """
    glyph = _glyph_for(name)
    return QIcon(_MaterialIconEngine(glyph, color))

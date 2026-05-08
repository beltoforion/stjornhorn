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
    "stop":         "e047",
    "save":         "e161",
    "save_as":      "eb60",
    "delete":       "e872",
    "zoom_out_map": "e56b",
    "fullscreen_exit": "e5d1",
    "view_stream": "e8f2",
    "view_column": "e8ec",
    "description":  "e873",
    "visibility":   "e8f4",
    "warning":      "e002",
    "refresh":      "e5d5",
    "push_pin":     "f10d",
    "select_all":   "e162",
    "unfold_more":  "e5d7",
    "unfold_less":  "e5d6",
    "vertical_split":   "e949",
    "horizontal_split": "e947",
    "settings":         "e8b8",
    # Step-over toggle on every skippable node's header.
    "redo":             "e15a",
    # Node-header glyphs. Keep grouped by the kind of node that uses
    # them so the table reads as a quick reference for which icons
    # are claimed by which area.
    # Sources / sinks
    "image":              "e3f4",
    "movie":              "e02c",
    "video_file":         "eb87",
    "table_chart":        "e265",
    "gradient":           "e3e9",
    "linear_scale":       "e260",
    "looks_one":          "e3fc",
    # Color / channels
    "palette":            "e40a",
    "invert_colors":      "e891",
    "filter_b_and_w":     "e3df",
    "color_lens":         "e3b7",
    "call_split":         "e0b6",
    "call_merge":         "e0b7",
    # Geometry / transform
    "crop":               "e3be",
    "rotate_right":       "e41a",
    "flip":               "e3e8",
    "photo_size_select_large": "e3c8",
    "zoom_in":            "e8ff",
    "open_with":          "e89f",
    # Filtering / processing
    "blur_on":            "e3a5",
    "blur_circular":      "e3a2",
    "exposure":           "e3ca",
    "contrast":           "eb37",
    "tune":               "e429",
    "grain":              "e3ec",
    "calculate":          "ea5f",
    "compare":            "e915",
    # Frequency / signal
    "graphic_eq":         "e1b8",
    "add":                "e145",
    # Visualization
    "show_chart":         "e6e1",
    "scatter_plot":       "e268",
    "polyline":           "ebbb",
    "analytics":          "ef3e",
    # Composition
    "layers":             "e53b",
    "opacity":            "ea5b",
    "grid_view":          "e9b0",
    # Control / streaming
    "schedule":           "e8b5",
    "repeat":             "e040",
    "timeline":           "e922",
    # Data / debug
    "format_list_numbered": "e242",
    "bug_report":         "e868",
    "info":               "e88e",
    "error":              "e000",
    "notifications":      "e7f4",
    "merge":              "eb98",
    "arrow_outward":      "f8ce",
    "vertical_align_center": "e240",
    # Header-action buttons
    "content_copy":       "e14d",
    "close":              "e5cd",
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


def paint_material_glyph(
    painter: QPainter,
    name: str,
    rect: QRect | "QRectF",
    *,
    color: QColor | None = None,
) -> None:
    """Draw a Material Icon glyph into ``rect`` using the active painter.

    Centred horizontally and vertically inside ``rect``, sized so the
    glyph's box matches ``rect.height()``. Used by widgets that paint
    their own chrome (e.g. ``NodeItem``'s header icon) and can't go
    through :class:`QIcon`, since a ``QIcon`` would need a separate
    pixmap render path. Both ``QRect`` and ``QRectF`` are accepted so
    callers can pass whichever they already have.
    """
    family = _ensure_font_loaded()
    glyph = _glyph_for(name)
    font = QFont(family)
    font.setPixelSize(max(1, int(rect.height())))
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    painter.setFont(font)
    if color is not None:
        painter.setPen(color)
    painter.drawText(
        rect, Qt.AlignmentFlag.AlignCenter, glyph
    )
    painter.restore()

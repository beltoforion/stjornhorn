"""Active-theme registry and re-exports.

The codebase reads design tokens via ``from ui.theme import X`` — node
body colour, link colour, the QSS sheet, palette entries, etc. To
keep that import surface stable while making the *concrete* values
swappable, every token now lives on a :class:`Theme` instance, and
this module:

1. picks one of the registered themes as the **active theme** at
   import time (default: :data:`NEON_THEME`),
2. flattens its dataclass fields into module-level globals so legacy
   ``from ui.theme import NODE_BODY_COLOR`` keeps working unchanged,
3. exposes :func:`apply_theme` to set the active theme and apply its
   palette / QSS to a running :class:`QApplication`.

Adding a new theme is "drop ``ui/themes/<name>.py``, build a
``Theme`` with the values you want, register it in
:data:`AVAILABLE_THEMES`". Consumer modules don't need to change.

Switching themes at runtime (after UI modules have already cached
the previous values) is **not** supported — call
:func:`apply_theme` once during app startup, before any
node/link/widget is constructed. ``main.apply_dark_theme(app)``
already does this in the right place.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from constants import ASSETS_DIR
from core.io_data import IoDataType


@dataclass(frozen=True)
class Theme:
    """All design tokens that drive the editor's look.

    A theme is a self-contained value: it carries every colour, the
    glow extent, the QSS stylesheet template (with ``@@…@@``
    placeholders for absolute asset paths) and the palette entries.
    The application owns one *active* :class:`Theme` at a time.

    Colour fields use :class:`QColor` so they can be passed to
    :class:`QBrush` / :class:`QPen` without conversion. Floats like
    :attr:`GLOW_RADIUS` are in scene pixels.
    """

    name: str

    # ── Node category accents ──
    #
    # Drive both the node border and its outer glow. The names still
    # read ``*_HEADER_COLOR`` because the dispatch in
    # :meth:`ui.node_item.NodeItem._header_color` keys off Source/
    # Filter/Sink and downstream callers expect those identifiers.
    SOURCE_HEADER_COLOR: QColor
    FILTER_HEADER_COLOR: QColor
    SINK_HEADER_COLOR: QColor
    NODE_SKIPPED_HEADER_COLOR: QColor

    # ── Node body ──
    NODE_BODY_COLOR: QColor
    NODE_HEADER_DIVIDER_COLOR: QColor
    NODE_BORDER_COLOR: QColor
    NODE_BORDER_SELECTED: QColor
    NODE_TITLE_TEXT_COLOR: QColor
    NODE_PARAM_LABEL_COLOR: QColor

    # ── Outer glow (nodes + links) ──
    NODE_GLOW_COLOR: QColor
    NODE_GLOW_SELECTED_COLOR: QColor
    GLOW_RADIUS: float

    # ── Ports ──
    PORT_INPUT_COLOR: QColor
    PORT_OUTPUT_COLOR: QColor
    PORT_HOVER_COLOR: QColor
    PORT_TYPE_COLORS: Mapping[IoDataType, QColor]
    PORT_TYPE_DEFAULT_COLOR: QColor
    PORT_DIRECTION_GLYPH_COLOR: QColor

    # ── Links ──
    LINK_COLOR: QColor
    LINK_SELECTED_COLOR: QColor
    LINK_PENDING_COLOR: QColor

    # ── Canvas ──
    CANVAS_BACKGROUND_COLOR: QColor
    CANVAS_GRID_COLOR: QColor

    # ── Status ──
    STATUS_OK_COLOR: QColor
    STATUS_FAIL_COLOR: QColor
    STATUS_MUTED_COLOR: QColor
    STATUS_WARN_COLOR: QColor

    # ── App palette ──
    PALETTE_WINDOW: QColor
    PALETTE_WINDOW_TEXT: QColor
    PALETTE_BASE: QColor
    PALETTE_ALT_BASE: QColor
    PALETTE_TEXT: QColor
    PALETTE_BUTTON: QColor
    PALETTE_BUTTON_TEXT: QColor
    PALETTE_HIGHLIGHT: QColor
    PALETTE_HIGHLIGHTED_TEXT: QColor

    # ── Stylesheet ──
    #
    # Asset-path placeholders (``@@SPINNER_UP@@`` etc.) are filled in
    # by :func:`apply_theme`; colours are baked in as hex literals so
    # a theme is fully self-contained.
    QSS_TEMPLATE: str = field(repr=False)


# Importing the bundled theme modules has to happen after :class:`Theme`
# is defined — they construct a :class:`Theme` instance at module load.
# Locked at import time; new themes added to ``ui/themes/`` should be
# appended here.
from ui.themes.neon import NEON_THEME  # noqa: E402

#: Registered themes by name. Add an entry here when introducing a
#: new theme module so callers can look it up by name (e.g. from a
#: persisted settings value).
AVAILABLE_THEMES: dict[str, Theme] = {
    NEON_THEME.name: NEON_THEME,
}

#: Default theme used when no explicit theme is selected.
DEFAULT_THEME: Theme = NEON_THEME

# The currently active theme. Mutated by :func:`apply_theme`; consumer
# modules read its fields via the module-level globals re-exported
# below.
_active_theme: Theme = DEFAULT_THEME


def get_active_theme() -> Theme:
    """Return the active :class:`Theme` instance."""
    return _active_theme


# Names re-exported as module-level globals for backwards-compat with
# the ``from ui.theme import X`` pattern that pre-dates the Theme
# abstraction. Asset-path placeholders are filled at apply time.
_REEXPORTED_FIELDS: tuple[str, ...] = tuple(
    f.name for f in Theme.__dataclass_fields__.values() if f.name != "QSS_TEMPLATE"
)


def _reexport(theme: Theme) -> None:
    """Copy the theme's fields into this module's globals so the
    legacy ``from ui.theme import NODE_BODY_COLOR`` keeps resolving
    against the active theme."""
    for name in _REEXPORTED_FIELDS:
        globals()[name] = getattr(theme, name)


_reexport(_active_theme)


def _resolve_qss(theme: Theme) -> str:
    """Substitute asset-path placeholders in the theme's QSS template
    with absolute paths to the bundled SVGs.

    ``as_posix()`` avoids backslash-escape headaches on Windows where
    QSS would otherwise treat ``\\u`` etc. as escape sequences inside
    the URL.
    """
    icons = ASSETS_DIR / "icons"
    return (
        theme.QSS_TEMPLATE
        .replace("@@SPINNER_UP@@",   (icons / "spinner_up.svg").as_posix())
        .replace("@@SPINNER_DOWN@@", (icons / "spinner_down.svg").as_posix())
        .replace("@@CHECKMARK@@",    (icons / "checkmark.svg").as_posix())
    )


def apply_theme(app: QApplication, theme: Theme | None = None) -> None:
    """Set the active theme and apply its palette + QSS to ``app``.

    Pass ``None`` to apply :data:`DEFAULT_THEME`. The active theme's
    fields are re-published as module-level globals so any code that
    reads ``ui.theme.NODE_BODY_COLOR`` (via attribute lookup, not a
    cached ``from ... import``) sees the new values.

    Call once early in startup, before any node / link / widget is
    constructed — those modules cache the values via
    ``from ui.theme import …`` and won't observe a later swap.
    """
    global _active_theme
    if theme is None:
        theme = DEFAULT_THEME
    _active_theme = theme
    _reexport(theme)

    palette = QPalette()
    palette.setColor(QPalette.Window,          theme.PALETTE_WINDOW)
    palette.setColor(QPalette.WindowText,      theme.PALETTE_WINDOW_TEXT)
    palette.setColor(QPalette.Base,            theme.PALETTE_BASE)
    palette.setColor(QPalette.AlternateBase,   theme.PALETTE_ALT_BASE)
    palette.setColor(QPalette.Text,            theme.PALETTE_TEXT)
    palette.setColor(QPalette.Button,          theme.PALETTE_BUTTON)
    palette.setColor(QPalette.ButtonText,      theme.PALETTE_BUTTON_TEXT)
    palette.setColor(QPalette.Highlight,       theme.PALETTE_HIGHLIGHT)
    palette.setColor(QPalette.HighlightedText, theme.PALETTE_HIGHLIGHTED_TEXT)
    app.setPalette(palette)

    app.setStyleSheet(_resolve_qss(theme))


def apply_dark_theme(app: QApplication) -> None:
    """Backwards-compat shim — applies :data:`DEFAULT_THEME`.

    Kept so existing callers (``main.py``) don't have to change. New
    code should call :func:`apply_theme` directly with an explicit
    :class:`Theme`.
    """
    apply_theme(app, DEFAULT_THEME)

"""Active-theme registry and re-exports.

The codebase reads design tokens via ``from ui.theme import X`` — node
body colour, link colour, the QSS sheet, palette entries, etc. To
keep that import surface stable while making the *concrete* values
swappable, every token now lives on a :class:`Theme` instance, and
this module:

1. picks one of the registered themes as the **active theme** at
   import time, choosing based on the ``theme_name`` field of the
   persisted settings file (default: :data:`NEON_THEME`),
2. flattens its dataclass fields into module-level globals so legacy
   ``from ui.theme import NODE_BODY_COLOR`` keeps working unchanged,
3. exposes :func:`apply_theme` to push the current active theme's
   palette / QSS onto a running :class:`QApplication`.

Adding a new theme is "drop ``ui/themes/<name>.py``, build a
``Theme`` with the values you want, register it in
:data:`AVAILABLE_THEMES`". Consumer modules don't need to change.

Theme switching is **startup-only** — the active theme is locked in
the moment ``ui.theme`` is imported, well before any
node/link/widget caches its values via ``from ui.theme import …``.
:class:`AppSettings.theme_name` writes the selection to disk; the
next launch picks it up here.
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
    glow strokes that the node / link painters should walk through,
    booleans that branch the painter (``HEADER_AS_STRIP``), the QSS
    stylesheet template (with ``@@…@@`` placeholders for absolute
    asset paths) and the palette entries.
    """

    name: str
    display_name: str

    # ── Node category accents ──
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

    #: Whether to render a solid coloured header strip at the top of
    #: each node (classic look) or drop the strip in favour of a thin
    #: category-coloured divider under the title row (neon look —
    #: the per-category identity then lives on the border + glow).
    HEADER_AS_STRIP: bool

    #: Whether the node border picks up the per-category accent
    #: (neon) or always uses :attr:`NODE_BORDER_COLOR` (classic, where
    #: the strip carries the category and the border is just a frame).
    BORDER_FROM_CATEGORY: bool

    # ── Outer glow (nodes + links) ──
    NODE_GLOW_COLOR: QColor
    NODE_GLOW_SELECTED_COLOR: QColor
    #: Glow passes drawn around each node body rect, ``(offset, alpha)``
    #: tuples walked from outermost-faintest to innermost-strongest.
    #: Empty disables the node glow entirely (classic theme).
    NODE_GLOW_STROKES: tuple[tuple[float, int], ...]
    #: Glow passes drawn under each bezier link path,
    #: ``(stroke_width, alpha)`` tuples. Empty disables the link halo
    #: (classic theme — wire stays a single hairline).
    LINK_GLOW_STROKES: tuple[tuple[float, int], ...]
    #: Width of the inner solid stroke painted on top of the link
    #: glow halo.
    LINK_STROKE_WIDTH: float

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
    QSS_TEMPLATE: str = field(repr=False)


# Importing the bundled theme modules has to happen after :class:`Theme`
# is defined — they construct a :class:`Theme` instance at module load.
from ui.themes.classic import CLASSIC_THEME  # noqa: E402
from ui.themes.neon import NEON_THEME        # noqa: E402

#: Registered themes by name. Add an entry here when introducing a
#: new theme module so callers can look it up by name (e.g. from a
#: persisted settings value).
AVAILABLE_THEMES: dict[str, Theme] = {
    NEON_THEME.name:    NEON_THEME,
    CLASSIC_THEME.name: CLASSIC_THEME,
}

#: Default theme used when no explicit theme is selected.
DEFAULT_THEME: Theme = NEON_THEME


def _persisted_theme() -> Theme:
    """Look up the persisted ``theme_name`` from the settings file
    and return the matching :class:`Theme`, or :data:`DEFAULT_THEME`
    if the setting is absent or names an unknown theme.

    Read directly from the JSON file rather than via
    :class:`ui.settings.AppSettings` because :class:`AppSettings`
    needs a :class:`QApplication`, and we run during module import —
    well before ``main()`` has constructed one.
    """
    # Local import to avoid a circular dependency: ``ui.settings``
    # imports nothing from ``ui.theme`` and we want to keep it that
    # way, but the converse path is fine.
    from ui.settings import SETTINGS_FILE, _read_settings_file
    name = _read_settings_file(SETTINGS_FILE).get("theme_name")
    if isinstance(name, str) and name in AVAILABLE_THEMES:
        return AVAILABLE_THEMES[name]
    return DEFAULT_THEME


# The currently active theme. Locked at module-import time based on
# the persisted setting. Not mutated thereafter.
_active_theme: Theme = _persisted_theme()


def get_active_theme() -> Theme:
    """Return the active :class:`Theme` instance."""
    return _active_theme


# Names re-exported as module-level globals for backwards-compat with
# the ``from ui.theme import X`` pattern that pre-dates the Theme
# abstraction.
_REEXPORTED_FIELDS: tuple[str, ...] = tuple(
    f.name for f in Theme.__dataclass_fields__.values()
    if f.name not in {"QSS_TEMPLATE", "name", "display_name"}
)


def _reexport(theme: Theme) -> None:
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
    """Apply ``theme`` (or the active one if ``None``) to ``app``.

    Sets :class:`QPalette` and the application stylesheet. Re-exports
    the theme's fields into this module's globals so that a swap
    invoked before any UI module has imported is fully effective.

    Switching themes after node / link / widget modules have already
    cached values via ``from ui.theme import …`` is **not**
    supported. The intended flow is:

      1. user picks a theme on the Settings page,
      2. :class:`AppSettings.theme_name` writes it to the settings
         file,
      3. on next launch, :func:`_persisted_theme` reads it back at
         ``ui.theme`` import time and locks it in.
    """
    global _active_theme
    if theme is None:
        theme = _active_theme
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
    """Backwards-compat shim — applies whichever theme is currently
    active (loaded from settings at module import).

    Kept so existing callers (``main.py``) don't have to change.
    """
    apply_theme(app)

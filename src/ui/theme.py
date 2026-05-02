from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from constants import ASSETS_DIR
from core.io_data import IoDataType

# ── Node accent colours by category ────────────────────────────────────────────
# These drive both the border and the outer glow on a node — the per-
# category neon hue is the only thing carrying "what kind of node is
# this" in the new style (the solid coloured header strip is gone). The
# names still read ``*_HEADER_COLOR`` because ``NodeItem._header_color()``
# already dispatches on Source/Filter/Sink and downstream callers
# expect the same identifiers; treat them as "category accent" colours.

SOURCE_HEADER_COLOR = QColor( 60, 175, 240)   # neon cyan-blue
FILTER_HEADER_COLOR = QColor( 60, 220, 220)   # neon cyan/teal
SINK_HEADER_COLOR   = QColor(230, 100, 200)   # neon magenta

#: Accent colour used when a node is skipped (bypassed). Muted slate so
#: the node visually recedes against the dark canvas and the user can
#: see at a glance that it's no longer doing work.
NODE_SKIPPED_HEADER_COLOR = QColor(110, 120, 140)

NODE_BODY_COLOR           = QColor( 18,  24,  44)
#: Subtle separator drawn under the title row to echo the inset panels
#: in the mockup. Picks the category accent at low alpha at paint time;
#: this constant is just the fallback line colour for non-categorised
#: paths.
NODE_HEADER_DIVIDER_COLOR = QColor( 80, 110, 150, 110)
NODE_BORDER_COLOR         = QColor( 80, 200, 240)
NODE_BORDER_SELECTED      = QColor(255, 220,  80)
NODE_TITLE_TEXT_COLOR     = QColor(225, 240, 255)
NODE_PARAM_LABEL_COLOR    = QColor(180, 205, 230)

#: Outer glow colours used by node and link painters to fake a neon
#: rim against the dark canvas. The painter walks outward from the body
#: rect / path in a few expanding strokes at decreasing alpha — see
#: :meth:`ui.node_item.NodeItem.paint` and
#: :meth:`ui.link_item.LinkItem.paint`.
NODE_GLOW_COLOR           = QColor( 80, 200, 240)
NODE_GLOW_SELECTED_COLOR  = QColor(255, 220,  80)
#: Outer-glow extent in scene pixels. The node and link bounding rects
#: are inflated by this amount so the glow strokes don't get clipped.
GLOW_RADIUS: float = 6.0

PORT_INPUT_COLOR          = QColor(210, 210, 210)
PORT_OUTPUT_COLOR         = QColor(220, 180,   0)
PORT_HOVER_COLOR          = QColor(255, 255, 255)

#: Per-:class:`~core.io_data.IoDataType` ring/fill colour for ports.
#:
#: A port whose ``accepted_types`` (input) or ``emits`` (output) set
#: contains *N* types is rendered as *N* equal arcs around the port
#: ring, each picking its colour from this map. The same palette
#: drives the connected-state pie-slice fill.
#:
#: The palette borrows from common node-editor conventions (Blender,
#: Houdini): images blue, numerics orange, structures green/violet,
#: booleans red. When introducing a new :class:`IoDataType`, add an
#: entry here so the UI doesn't fall back to the neutral default.
PORT_TYPE_COLORS: dict[IoDataType, QColor] = {
    IoDataType.IMAGE:       QColor( 59, 130, 246),  # blue
    IoDataType.IMAGE_GREY:  QColor(156, 163, 175),  # light grey
    IoDataType.SCALAR:      QColor(245, 158,  11),  # orange
    IoDataType.MATRIX:      QColor(139,  92, 246),  # violet
    IoDataType.DATASET:     QColor( 16, 185, 129),  # green
    IoDataType.BOOL:        QColor(239,  68,  68),  # red
    IoDataType.STRING:      QColor( 20, 184, 166),  # teal
    IoDataType.ENUM:        QColor(236,  72, 153),  # pink
    IoDataType.PATH:        QColor(161,  98,   7),  # brown
}

#: Fallback ring colour used by :class:`~ui.port_item.PortItem` for any
#: :class:`IoDataType` not present in :data:`PORT_TYPE_COLORS` — keeps
#: the UI usable while a new type is being added without forcing a
#: theme update in the same patch. Same neutral grey as the legacy
#: input ring.
PORT_TYPE_DEFAULT_COLOR   = QColor(210, 210, 210)

#: Glyph colour for the small triangle drawn beside an output port to
#: signal flow direction. Light grey so it reads against both the
#: canvas background and the node body without competing with the
#: type-coloured ring.
PORT_DIRECTION_GLYPH_COLOR = QColor(210, 210, 210)

LINK_COLOR                = QColor(110, 215, 255)
LINK_SELECTED_COLOR       = QColor(255, 110, 220)
LINK_PENDING_COLOR        = QColor(150, 200, 230)

CANVAS_BACKGROUND_COLOR   = QColor( 10,  14,  30)
CANVAS_GRID_COLOR         = QColor( 28,  38,  70)

STATUS_OK_COLOR    = QColor( 80, 220, 160)
STATUS_FAIL_COLOR  = QColor(255, 100, 130)
STATUS_MUTED_COLOR = QColor(140, 160, 180)
#: Amber used for transient "attention, but not an error" affordances —
#: e.g. the unsaved-changes dot in the editor status widget.
STATUS_WARN_COLOR  = QColor(255, 200,  80)


_DARK_QSS = """
QMainWindow, QWidget {
    background-color: #0a0e1e;
    color: #dceaf5;
}
QDockWidget {
    color: #dceaf5;
    titlebar-close-icon: none;
}
QDockWidget::title {
    background: #121830;
    padding: 4px;
    border-bottom: 1px solid #1c2646;
}
QToolBar {
    background: #0d1226;
    border: 0;
    spacing: 6px;
    padding: 6px;
}
QToolButton, QPushButton {
    background: #141b34;
    border: 1px solid #2a3a66;
    padding: 4px 10px;
    border-radius: 6px;
    color: #dceaf5;
}
QToolButton:hover, QPushButton:hover {
    background: #1c2750;
    border-color: #50c8f0;
    color: #e8f6ff;
}
QToolButton:pressed, QPushButton:pressed {
    background: #0e1428;
}
QToolButton:checked {
    background: #1a2a55;
    border-color: #50c8f0;
    color: #b0eaff;
}
QToolButton:checked:hover {
    background: #20335f;
}
QPushButton:disabled {
    background: #11162a;
    color: #5a6680;
    border-color: #1c2646;
}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background: #0e1428;
    border: 1px solid #1c2646;
    padding: 3px 6px;
    color: #dceaf5;
    selection-background-color: #1a3a6a;
    border-radius: 4px;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border-color: #50c8f0;
}
/* Touching ``padding`` on a QSpinBox / QDoubleSpinBox above stops Qt
   from rendering the up/down arrow sub-controls in their native
   geometry — the OS style positions them by a fixed offset from the
   right edge that the padding pushes the text into. ``padding-right:
   18px`` reserves a 16-px button column plus 2 px of breathing room
   so the buttons sit at the right edge without overlapping the text.
   The button geometry rules pin the up/down half to the top-right
   and bottom-right of the border, with a 1-px dark separator on the
   left. The arrow images are inline SVG data URIs (light grey
   triangles) so the buttons keep visible chevrons regardless of the
   OS native style — without the explicit image, the stylesheet-mode
   rendering kicks in and Qt's default arrow drawing drops out. */
QSpinBox, QDoubleSpinBox {
    padding-right: 18px;
}
QSpinBox::up-button, QDoubleSpinBox::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 16px;
    border-left: 1px solid #1c2646;
}
QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 16px;
    border-left: 1px solid #1c2646;
}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
    image: url("@@SPINNER_UP@@");
    width: 7px;
    height: 7px;
}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    image: url("@@SPINNER_DOWN@@");
    width: 7px;
    height: 7px;
}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
    background: #1a2750;
}
QSpinBox::up-button:pressed, QDoubleSpinBox::up-button:pressed,
QSpinBox::down-button:pressed, QDoubleSpinBox::down-button:pressed {
    background: #243766;
}
/* QComboBox sub-controls are dropped from the native render the
   moment the QComboBox gets any stylesheet rule (background /
   border / padding above), same as the QSpinBox case. We pin the
   drop-down's geometry to the right edge and reuse the
   ``spinner_down.svg`` chevron so the picker has a visible
   affordance. */
QComboBox {
    padding-right: 18px;
}
QComboBox::drop-down {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 16px;
    border-left: 1px solid #1c2646;
}
QComboBox::down-arrow {
    image: url("@@SPINNER_DOWN@@");
    width: 7px;
    height: 7px;
}
QComboBox::drop-down:hover {
    background: #1a2750;
}
QListWidget, QTreeView {
    background: #0e1428;
    border: 1px solid #1c2646;
    color: #dceaf5;
}
QListWidget::item:selected, QTreeView::item:selected {
    background: #1a3a6a;
    color: #e8f6ff;
}
QStatusBar {
    background: #0d1226;
    border-top: 1px solid #1c2646;
}
QMenuBar {
    background: #0d1226;
    color: #dceaf5;
}
QMenuBar::item:selected {
    background: #1a3a6a;
}
QMenu {
    background: #0d1226;
    border: 1px solid #1c2646;
    color: #dceaf5;
}
QMenu::item:selected {
    background: #1a3a6a;
}
QLabel[muted="true"] {
    color: #7a90ad;
}
QCheckBox {
    color: #dceaf5;
    spacing: 6px;
    background: transparent;
}
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    background: #0e1428;
    border: 1px solid #2a3a66;
    border-radius: 3px;
}
QCheckBox::indicator:hover {
    border-color: #50c8f0;
}
QCheckBox::indicator:checked {
    background: #1a3a6a;
    border-color: #50c8f0;
    /* Without an explicit ``image`` Qt's stylesheet rendering mode
       fills the indicator's background but never draws the actual
       check glyph. The SVG is sized to 14×14 to match the indicator
       and uses a light stroke so it reads against the blue fill. */
    image: url("@@CHECKMARK@@");
}
QCheckBox::indicator:disabled {
    background: #11162a;
    border-color: #1c2646;
}
QScrollBar:vertical, QScrollBar:horizontal {
    background: #0d1226;
    border: none;
}
QScrollBar:vertical { width: 12px; }
QScrollBar:horizontal { height: 12px; }
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: #243766;
    border-radius: 4px;
    min-height: 24px;
    min-width: 24px;
}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {
    background: #2f4a85;
}
QScrollBar::add-line, QScrollBar::sub-line { background: transparent; height: 0; width: 0; }
QSplitter::handle {
    background: #1c2646;
}
QTabBar::tab {
    background: #0d1226;
    color: #b0c4d8;
    padding: 6px 12px;
    border: 1px solid #1c2646;
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}
QTabBar::tab:selected {
    background: #141b34;
    color: #e8f6ff;
    border-color: #2a3a66;
}
QTabBar::tab:hover {
    color: #e8f6ff;
}
"""


def apply_dark_theme(app: QApplication) -> None:
    """Apply a dark palette + QSS sheet to the whole application."""
    palette = QPalette()
    palette.setColor(QPalette.Window,          QColor( 10,  14,  30))
    palette.setColor(QPalette.WindowText,      QColor(220, 234, 245))
    palette.setColor(QPalette.Base,            QColor( 14,  20,  40))
    palette.setColor(QPalette.AlternateBase,   QColor( 18,  24,  48))
    palette.setColor(QPalette.Text,            QColor(220, 234, 245))
    palette.setColor(QPalette.Button,          QColor( 20,  27,  52))
    palette.setColor(QPalette.ButtonText,      QColor(220, 234, 245))
    palette.setColor(QPalette.Highlight,       QColor( 26,  58, 106))
    palette.setColor(QPalette.HighlightedText, QColor(232, 246, 255))
    app.setPalette(palette)

    # Resolve absolute paths to the SVG arrow assets so the QSS
    # ``url(...)`` references work regardless of the process's current
    # working directory. as_posix() avoids backslash-escape headaches
    # on Windows where QSS would otherwise treat ``\u`` etc. as escape
    # sequences inside the URL.
    icons = ASSETS_DIR / "icons"
    qss = (
        _DARK_QSS
        .replace("@@SPINNER_UP@@",   (icons / "spinner_up.svg").as_posix())
        .replace("@@SPINNER_DOWN@@", (icons / "spinner_down.svg").as_posix())
        .replace("@@CHECKMARK@@",    (icons / "checkmark.svg").as_posix())
    )
    app.setStyleSheet(qss)

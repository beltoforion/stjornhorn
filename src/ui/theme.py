from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from constants import ASSETS_DIR
from core.io_data import IoDataType

# ── Node header colours by category ────────────────────────────────────────────
# RGBA tuples; kept separate from the QSS sheet so node-drawing code can
# bind them directly to QBrush/QPen without parsing stylesheet strings.

SOURCE_HEADER_COLOR = QColor(24, 168, 255)
FILTER_HEADER_COLOR = QColor(130, 82, 255)
SINK_HEADER_COLOR   = QColor(255, 150, 42)

#: Header colour used when a node is skipped (bypassed). Muted grey so
#: the node visually recedes and the user can see at a glance that it's
#: no longer doing work.
NODE_SKIPPED_HEADER_COLOR = QColor(82, 90, 122)

NODE_BODY_COLOR           = QColor(10, 18, 48)
NODE_BORDER_COLOR         = QColor(46, 92, 186)
NODE_BORDER_SELECTED      = QColor(97, 234, 255)
NODE_TITLE_TEXT_COLOR     = QColor(231, 244, 255)
NODE_PARAM_LABEL_COLOR    = QColor(185, 209, 241)

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

LINK_COLOR                = QColor(124, 165, 255)
LINK_SELECTED_COLOR       = QColor(255, 98, 230)
LINK_PENDING_COLOR        = QColor(86, 112, 179)

CANVAS_BACKGROUND_COLOR   = QColor(6, 13, 43)
CANVAS_GRID_COLOR         = QColor(22, 43, 102)

STATUS_OK_COLOR    = QColor( 90, 200, 100)
STATUS_FAIL_COLOR  = QColor(220,  80,  80)
STATUS_MUTED_COLOR = QColor(140, 140, 140)
#: Amber used for transient "attention, but not an error" affordances —
#: e.g. the unsaved-changes dot in the editor status widget.
STATUS_WARN_COLOR  = QColor(230, 170,  50)


_DARK_QSS = """
QMainWindow, QWidget {
    background-color: #061136;
    color: #dce8ff;
}
QDockWidget {
    color: #dce8ff;
    titlebar-close-icon: none;
}
QDockWidget::title {
    background: #0f1d53;
    padding: 4px;
    border-bottom: 1px solid #1f3d8a;
}
QToolBar {
    background: #0a1747;
    border: 0;
    spacing: 4px;
    padding: 4px;
}
QToolButton, QPushButton {
    background: #12265f;
    border: 1px solid #2447a2;
    padding: 4px 10px;
    border-radius: 3px;
    color: #dce8ff;
}
QToolButton:hover, QPushButton:hover {
    background: #1a3580;
}
QToolButton:pressed, QPushButton:pressed {
    background: #0b1a4a;
}
QToolButton:checked {
    background: #3157df;
    border-color: #64e8ff;
}
QToolButton:checked:hover {
    background: #4a61f0;
}
QPushButton:disabled {
    background: #0d1e55;
    color: #6f87c0;
    border-color: #1b3478;
}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background: #0a1440;
    border: 1px solid #2447a2;
    padding: 3px 6px;
    color: #dce8ff;
    selection-background-color: #2e65ff;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border-color: #63d3ff;
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
    border-left: 1px solid #1f3d8a;
}
QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 16px;
    border-left: 1px solid #1f3d8a;
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
    background: #0d1e55;
}
QSpinBox::up-button:pressed, QDoubleSpinBox::up-button:pressed,
QSpinBox::down-button:pressed, QDoubleSpinBox::down-button:pressed {
    background: #1a3277;
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
    border-left: 1px solid #1f3d8a;
}
QComboBox::down-arrow {
    image: url("@@SPINNER_DOWN@@");
    width: 7px;
    height: 7px;
}
QComboBox::drop-down:hover {
    background: #0d1e55;
}
QListWidget, QTreeView {
    background: #0a1440;
    border: 1px solid #2447a2;
    color: #dce8ff;
}
QListWidget::item:selected, QTreeView::item:selected {
    background: #3157df;
}
QStatusBar {
    background: #0a1747;
    border-top: 1px solid #1f3d8a;
}
QMenuBar {
    background: #0a1747;
    color: #dce8ff;
}
QMenuBar::item:selected {
    background: #3157df;
}
QMenu {
    background: #0a1747;
    border: 1px solid #2447a2;
}
QMenu::item:selected {
    background: #3157df;
}
QLabel[muted="true"] {
    color: #8da6d9;
}
QCheckBox {
    color: #dce8ff;
    spacing: 6px;
    background: transparent;
}
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    background: #0a1440;
    border: 1px solid #4f74cf;
    border-radius: 2px;
}
QCheckBox::indicator:hover {
    border-color: #74ccff;
}
QCheckBox::indicator:checked {
    background: #3157df;
    border-color: #7ff2ff;
    /* Without an explicit ``image`` Qt's stylesheet rendering mode
       fills the indicator's background but never draws the actual
       check glyph. The SVG is sized to 14×14 to match the indicator
       and uses a light stroke so it reads against the blue fill. */
    image: url("@@CHECKMARK@@");
}
QCheckBox::indicator:disabled {
    background: #0d1e55;
    border-color: #1b3478;
}
"""


def apply_dark_theme(app: QApplication) -> None:
    """Apply a dark palette + QSS sheet to the whole application."""
    palette = QPalette()
    palette.setColor(QPalette.Window,          QColor(38, 38, 41))
    palette.setColor(QPalette.WindowText,      QColor(224, 224, 224))
    palette.setColor(QPalette.Base,            QColor(31, 31, 34))
    palette.setColor(QPalette.AlternateBase,   QColor(38, 38, 41))
    palette.setColor(QPalette.Text,            QColor(224, 224, 224))
    palette.setColor(QPalette.Button,          QColor(58, 58, 63))
    palette.setColor(QPalette.ButtonText,      QColor(224, 224, 224))
    palette.setColor(QPalette.Highlight,       QColor(58, 91, 138))
    palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
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

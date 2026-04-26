from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

# ── Node header colours by category ────────────────────────────────────────────
# RGBA tuples; kept separate from the QSS sheet so node-drawing code can
# bind them directly to QBrush/QPen without parsing stylesheet strings.

SOURCE_HEADER_COLOR = QColor(30, 100, 180)
FILTER_HEADER_COLOR = QColor(30, 140,  60)
SINK_HEADER_COLOR   = QColor(180, 100, 20)

#: Header colour used when a node is skipped (bypassed). Muted grey so
#: the node visually recedes and the user can see at a glance that it's
#: no longer doing work.
NODE_SKIPPED_HEADER_COLOR = QColor(110, 110, 115)

NODE_BODY_COLOR           = QColor(48, 48, 52)
NODE_BORDER_COLOR         = QColor(20, 20, 22)
NODE_BORDER_SELECTED      = QColor(240, 200,  60)
NODE_TITLE_TEXT_COLOR     = QColor(250, 250, 250)
NODE_PARAM_LABEL_COLOR    = QColor(210, 210, 210)

PORT_INPUT_COLOR          = QColor(210, 210, 210)
PORT_OUTPUT_COLOR         = QColor(220, 180,   0)
PORT_HOVER_COLOR          = QColor(255, 255, 255)

LINK_COLOR                = QColor(180, 180, 180)
LINK_SELECTED_COLOR       = QColor(240, 200,   0)
LINK_PENDING_COLOR        = QColor(150, 150, 150)

CANVAS_BACKGROUND_COLOR   = QColor(36, 36, 40)
CANVAS_GRID_COLOR         = QColor(56, 56, 60)

STATUS_OK_COLOR    = QColor( 90, 200, 100)
STATUS_FAIL_COLOR  = QColor(220,  80,  80)
STATUS_MUTED_COLOR = QColor(140, 140, 140)
#: Amber used for transient "attention, but not an error" affordances —
#: e.g. the unsaved-changes dot in the editor status widget.
STATUS_WARN_COLOR  = QColor(230, 170,  50)


_DARK_QSS = """
QMainWindow, QWidget {
    background-color: #262629;
    color: #e0e0e0;
}
QDockWidget {
    color: #e0e0e0;
    titlebar-close-icon: none;
}
QDockWidget::title {
    background: #323236;
    padding: 4px;
    border-bottom: 1px solid #1a1a1d;
}
QToolBar {
    background: #2a2a2d;
    border: 0;
    spacing: 4px;
    padding: 4px;
}
QToolButton, QPushButton {
    background: #3a3a3f;
    border: 1px solid #1a1a1d;
    padding: 4px 10px;
    border-radius: 3px;
    color: #e0e0e0;
}
QToolButton:hover, QPushButton:hover {
    background: #4a4a50;
}
QToolButton:pressed, QPushButton:pressed {
    background: #2c2c30;
}
QToolButton:checked {
    background: #3a5b8a;
    border-color: #5a7bb0;
}
QToolButton:checked:hover {
    background: #456bac;
}
QPushButton:disabled {
    background: #2d2d30;
    color: #707070;
    border-color: #1a1a1d;
}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background: #1f1f22;
    border: 1px solid #1a1a1d;
    padding: 3px 6px;
    color: #e0e0e0;
    selection-background-color: #3a5b8a;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border-color: #5a5a60;
}
/* Touching ``padding`` on a QSpinBox / QDoubleSpinBox above stops Qt
   from rendering the up/down arrow sub-controls in their native
   geometry — the OS style positions them by a fixed offset from the
   right edge that the padding pushes the text into. We override the
   sub-control geometry explicitly so the text and the buttons stop
   overlapping each other. ``padding-right: 18px`` reserves the
   16-px button column plus a couple of pixels of breathing room. */
QSpinBox, QDoubleSpinBox {
    padding-right: 18px;
}
QSpinBox::up-button, QDoubleSpinBox::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 16px;
    border-left: 1px solid #1a1a1d;
}
QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 16px;
    border-left: 1px solid #1a1a1d;
}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow,
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    width: 7px;
    height: 7px;
}
QListWidget, QTreeView {
    background: #1f1f22;
    border: 1px solid #1a1a1d;
    color: #e0e0e0;
}
QListWidget::item:selected, QTreeView::item:selected {
    background: #3a5b8a;
}
QStatusBar {
    background: #2a2a2d;
    border-top: 1px solid #1a1a1d;
}
QMenuBar {
    background: #2a2a2d;
    color: #e0e0e0;
}
QMenuBar::item:selected {
    background: #3a5b8a;
}
QMenu {
    background: #2a2a2d;
    border: 1px solid #1a1a1d;
}
QMenu::item:selected {
    background: #3a5b8a;
}
QLabel[muted="true"] {
    color: #909090;
}
QCheckBox {
    color: #e0e0e0;
    spacing: 6px;
    background: transparent;
}
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    background: #1f1f22;
    border: 1px solid #5a5a60;
    border-radius: 2px;
}
QCheckBox::indicator:hover {
    border-color: #7a7a85;
}
QCheckBox::indicator:checked {
    background: #3a5b8a;
    border-color: #e0c040;
}
QCheckBox::indicator:disabled {
    background: #2d2d30;
    border-color: #1a1a1d;
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
    app.setStyleSheet(_DARK_QSS)

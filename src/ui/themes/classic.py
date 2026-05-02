"""The "Classic" theme — flat dark grey palette with solid coloured
node header strips, no neon glow, single-stroke wires.

This is the look Stjörnhorn shipped before the neon restyle. Kept as
a swappable theme for users who prefer the higher-contrast,
chrome-light original.
"""
from __future__ import annotations

from PySide6.QtGui import QColor

from core.io_data import IoDataType
from ui.theme import Theme

_QSS = """
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
    background: #2d2d30;
}
QSpinBox::up-button:pressed, QDoubleSpinBox::up-button:pressed,
QSpinBox::down-button:pressed, QDoubleSpinBox::down-button:pressed {
    background: #3a3a3e;
}
QComboBox {
    padding-right: 18px;
}
QComboBox::drop-down {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 16px;
    border-left: 1px solid #1a1a1d;
}
QComboBox::down-arrow {
    image: url("@@SPINNER_DOWN@@");
    width: 7px;
    height: 7px;
}
QComboBox::drop-down:hover {
    background: #2d2d30;
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
    image: url("@@CHECKMARK@@");
}
QCheckBox::indicator:disabled {
    background: #2d2d30;
    border-color: #1a1a1d;
}
"""


CLASSIC_THEME = Theme(
    name="classic",
    display_name="Classic",

    # ── Node category accents ──
    SOURCE_HEADER_COLOR=QColor( 30, 100, 180),
    FILTER_HEADER_COLOR=QColor( 30, 140,  60),
    SINK_HEADER_COLOR  =QColor(180, 100,  20),
    NODE_SKIPPED_HEADER_COLOR=QColor(110, 110, 115),

    # ── Node body ──
    NODE_BODY_COLOR          =QColor( 48,  48,  52),
    NODE_HEADER_DIVIDER_COLOR=QColor( 20,  20,  22, 200),
    NODE_BORDER_COLOR        =QColor( 20,  20,  22),
    NODE_BORDER_SELECTED     =QColor(240, 200,  60),
    NODE_TITLE_TEXT_COLOR    =QColor(250, 250, 250),
    NODE_PARAM_LABEL_COLOR   =QColor(210, 210, 210),
    HEADER_AS_STRIP=True,
    BORDER_FROM_CATEGORY=False,

    # ── Outer glow (disabled in the classic look) ──
    NODE_GLOW_COLOR         =QColor( 80, 200, 240),
    NODE_GLOW_SELECTED_COLOR=QColor(240, 200,  60),
    NODE_GLOW_STROKES=(),
    LINK_GLOW_STROKES=(),
    LINK_STROKE_WIDTH=2.0,

    # ── Ports ──
    PORT_INPUT_COLOR =QColor(210, 210, 210),
    PORT_OUTPUT_COLOR=QColor(220, 180,   0),
    PORT_HOVER_COLOR =QColor(255, 255, 255),
    PORT_TYPE_COLORS={
        IoDataType.IMAGE:       QColor( 59, 130, 246),
        IoDataType.IMAGE_GREY:  QColor(156, 163, 175),
        IoDataType.SCALAR:      QColor(245, 158,  11),
        IoDataType.MATRIX:      QColor(139,  92, 246),
        IoDataType.DATASET:     QColor( 16, 185, 129),
        IoDataType.BOOL:        QColor(239,  68,  68),
        IoDataType.STRING:      QColor( 20, 184, 166),
        IoDataType.ENUM:        QColor(236,  72, 153),
        IoDataType.PATH:        QColor(161,  98,   7),
    },
    PORT_TYPE_DEFAULT_COLOR   =QColor(210, 210, 210),
    PORT_DIRECTION_GLYPH_COLOR=QColor(210, 210, 210),

    # ── Links ──
    LINK_COLOR         =QColor(180, 180, 180),
    LINK_SELECTED_COLOR=QColor(240, 200,   0),
    LINK_PENDING_COLOR =QColor(150, 150, 150),

    # ── Canvas ──
    CANVAS_BACKGROUND_COLOR=QColor( 36,  36,  40),
    CANVAS_GRID_COLOR      =QColor( 56,  56,  60),

    # ── Status ──
    STATUS_OK_COLOR   =QColor( 90, 200, 100),
    STATUS_FAIL_COLOR =QColor(220,  80,  80),
    STATUS_MUTED_COLOR=QColor(140, 140, 140),
    STATUS_WARN_COLOR =QColor(230, 170,  50),

    # ── App palette ──
    PALETTE_WINDOW          =QColor( 38,  38,  41),
    PALETTE_WINDOW_TEXT     =QColor(224, 224, 224),
    PALETTE_BASE            =QColor( 31,  31,  34),
    PALETTE_ALT_BASE        =QColor( 38,  38,  41),
    PALETTE_TEXT            =QColor(224, 224, 224),
    PALETTE_BUTTON          =QColor( 58,  58,  63),
    PALETTE_BUTTON_TEXT     =QColor(224, 224, 224),
    PALETTE_HIGHLIGHT       =QColor( 58,  91, 138),
    PALETTE_HIGHLIGHTED_TEXT=QColor(255, 255, 255),

    QSS_TEMPLATE=_QSS,
)

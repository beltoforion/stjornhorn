from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QWidget,
)

from core.io_data import IoDataType
from ui.theme import (
    PORT_DIRECTION_GLYPH_COLOR,
    PORT_TYPE_COLORS,
    PORT_TYPE_DEFAULT_COLOR,
)

# Display label per IoDataType. Decoupled from the enum's ``value``
# (which doubles as the persistence token in saved flows) so the
# legend can read in plain English without renaming the enum.
_TYPE_LABELS: dict[IoDataType, str] = {
    IoDataType.IMAGE:      "Image",
    IoDataType.IMAGE_GREY: "Image (grey)",
    IoDataType.SCALAR:     "Scalar",
    IoDataType.MATRIX:     "Matrix",
    IoDataType.DATASET:    "Dataset",
    IoDataType.BOOL:       "Bool",
    IoDataType.STRING:     "String",
    IoDataType.ENUM:       "Enum",
    IoDataType.PATH:       "Path",
}


class _Swatch(QWidget):
    """Tiny port-shaped widget used for legend rows.

    Renders the same darker-fill + bright-ring shape as
    :class:`ui.port_item.PortItem` so the legend reads as a 1:1
    miniature of an actual port. Optional knobs let the caller pick
    the ring stroke style (solid/dotted), ring thickness (mirroring
    required vs. optional ports), and whether to draw the small
    right-pointing glyph (mirroring outputs).
    """

    DOT_SIZE: int = 12
    _RING_WIDTH_DEFAULT: float = 1.4
    _RING_WIDTH_THIN: float = 1.0
    _FILL_DARKEN: int = 200

    # Glyph geometry — kept in sync with PortItem's output triangle so
    # the legend mirrors the canvas without numeric drift.
    _GLYPH_BASE_OFFSET: float = 1.0
    _GLYPH_LENGTH: float = 4.5
    _GLYPH_HALF_HEIGHT: float = 3.0

    def __init__(
        self,
        color: QColor,
        *,
        ring_width: float = _RING_WIDTH_DEFAULT,
        ring_style: Qt.PenStyle = Qt.PenStyle.SolidLine,
        show_glyph: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._color = color
        self._ring_width = ring_width
        self._ring_style = ring_style
        self._show_glyph = show_glyph
        # Reserve glyph space on the right side so the dot stays
        # left-aligned with neighbouring (glyph-less) swatches in the
        # grid.
        extra = (self._GLYPH_BASE_OFFSET + self._GLYPH_LENGTH + 1.0) if show_glyph else 0.0
        self.setFixedSize(int(self.DOT_SIZE + extra), self.DOT_SIZE)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # Inset the rect by half the pen width so the ring sits inside
        # the widget bounds and isn't clipped on either side.
        inset = self._ring_width / 2
        rect = QRectF(inset, inset, self.DOT_SIZE - 2 * inset, self.DOT_SIZE - 2 * inset)

        painter.setPen(QPen(Qt.PenStyle.NoPen))
        painter.setBrush(QBrush(self._color.darker(self._FILL_DARKEN)))
        painter.drawEllipse(rect)

        painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        painter.setPen(QPen(self._color, self._ring_width, self._ring_style))
        painter.drawEllipse(rect)

        if self._show_glyph:
            cy = self.DOT_SIZE / 2
            base_x = self.DOT_SIZE - inset + self._GLYPH_BASE_OFFSET
            tip_x = base_x + self._GLYPH_LENGTH
            h = self._GLYPH_HALF_HEIGHT
            path = QPainterPath()
            path.moveTo(base_x, cy - h)
            path.lineTo(tip_x, cy)
            path.lineTo(base_x, cy + h)
            path.closeSubpath()
            painter.setPen(QPen(Qt.PenStyle.NoPen))
            painter.setBrush(QBrush(PORT_DIRECTION_GLYPH_COLOR))
            painter.drawPath(path)


class PortLegend(QFrame):
    """Floating legend explaining the port visual language.

    Parented to :class:`~ui.flow_view.FlowView` (the
    :class:`QAbstractScrollArea`, *not* its ``viewport()``) and pinned
    to the bottom-left corner of that widget. The view's viewport is
    just one of FlowView's children, so the legend sits as a sibling
    that overlays the canvas through normal Qt widget compositing —
    no scene item, no proxy, no per-frame repositioning. Pan and zoom
    only repaint the viewport, so the legend stays put automatically;
    only window resizes need a reposition (handled via an event
    filter on the parent).

    Two sections:
      * **Port types** — one row per :class:`IoDataType` showing the
        colour used for that type's ring and (darker) fill.
      * **Port roles** — required / optional / latched input
        variants and the output glyph, all rendered in the neutral
        default colour so the variation is purely about ring stroke
        and direction marker rather than type colour.
    """

    MARGIN: int = 12

    # Background opacity is baked into the stylesheet's rgba() rather
    # than applied via :class:`QGraphicsOpacityEffect`. The effect-based
    # path interacts badly with :class:`~PySide6.QtWidgets.QGraphicsView`'s
    # incremental update modes; the rgba fill bypasses the effect
    # pipeline entirely.
    _STYLE: str = """
        QFrame#PortLegend {
            background: rgba(31, 31, 34, 220);
            border: 1px solid #3a3a3f;
            border-radius: 4px;
        }
        QLabel#PortLegendTitle {
            color: #d0d0d0;
            font-weight: bold;
            background: transparent;
        }
        QLabel.PortLegendItem {
            color: #c8c8c8;
            background: transparent;
        }
        QToolButton#PortLegendClose {
            color: #c8c8c8;
            background: transparent;
            border: none;
            padding: 0 4px;
            font-size: 12px;
        }
        QToolButton#PortLegendClose:hover {
            color: #ffffff;
        }
    """

    #: Emitted when the user clicks the close button. The owning page
    #: handles this by flipping ``AppSettings.port_legend_visible``,
    #: which then propagates back to actually hide the widget — keeps
    #: the close click and the View-menu toggle on a single source of
    #: truth.
    close_requested = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("PortLegend")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setStyleSheet(self._STYLE)

        layout = QGridLayout(self)
        layout.setContentsMargins(10, 8, 12, 8)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(4)

        row = 0
        row = self._add_section(
            layout, row, "Port types", self._type_rows(), with_close_button=True,
        )
        row = self._add_section(layout, row, "Port roles", self._role_rows())

        self.adjustSize()
        # Stay anchored to the parent's bottom-left edge through window
        # resizes. Pan and zoom don't fire a Resize on the parent
        # (only on its viewport child), so this filter keeps the
        # legend completely still during canvas interaction.
        parent.installEventFilter(self)
        self._reposition()

    # ── Row builders ───────────────────────────────────────────────────────────

    def _type_rows(self) -> list[tuple[_Swatch, str]]:
        rows: list[tuple[_Swatch, str]] = []
        for t in IoDataType:
            color = PORT_TYPE_COLORS.get(t, PORT_TYPE_DEFAULT_COLOR)
            rows.append((_Swatch(color, parent=self), _TYPE_LABELS.get(t, t.value)))
        return rows

    def _role_rows(self) -> list[tuple[_Swatch, str]]:
        # Neutral colour so the variation reads as ring-style only —
        # the type-colour story stays in the upper section.
        c = PORT_TYPE_DEFAULT_COLOR
        return [
            (
                _Swatch(c, ring_width=_Swatch._RING_WIDTH_DEFAULT, parent=self),
                "Required input",
            ),
            (
                _Swatch(c, ring_width=_Swatch._RING_WIDTH_THIN, parent=self),
                "Optional input",
            ),
            (
                _Swatch(
                    c,
                    ring_width=_Swatch._RING_WIDTH_DEFAULT,
                    ring_style=Qt.PenStyle.DotLine,
                    parent=self,
                ),
                "Latched input (holds last value)",
            ),
            (
                _Swatch(c, show_glyph=True, parent=self),
                "Output",
            ),
        ]

    def _add_section(
        self,
        layout: QGridLayout,
        start_row: int,
        title_text: str,
        rows: list[tuple[_Swatch, str]],
        *,
        with_close_button: bool = False,
    ) -> int:
        # First section sits flush; subsequent ones leave a small gap by
        # adding extra vertical room on the title row.
        title = QLabel(title_text)
        title.setObjectName("PortLegendTitle")
        if start_row > 0:
            title.setContentsMargins(0, 8, 0, 0)

        if with_close_button:
            # Wrap title + close button in a horizontal sub-layout so
            # the close glyph anchors to the right edge of the legend.
            header = QHBoxLayout()
            header.setContentsMargins(0, 0, 0, 0)
            header.setSpacing(8)
            header.addWidget(title)
            header.addStretch(1)
            close = QToolButton(self)
            close.setObjectName("PortLegendClose")
            close.setText("✕")  # multiplication X
            close.setToolTip("Hide legend (View ▸ Port Legend to show)")
            close.setCursor(Qt.CursorShape.PointingHandCursor)
            close.clicked.connect(self.close_requested)
            header.addWidget(close)
            layout.addLayout(header, start_row, 0, 1, 2)
        else:
            layout.addWidget(title, start_row, 0, 1, 2)

        next_row = start_row + 1
        for swatch, text in rows:
            label = QLabel(text)
            label.setProperty("class", "PortLegendItem")
            layout.addWidget(swatch, next_row, 0)
            layout.addWidget(label, next_row, 1)
            next_row += 1
        return next_row

    # ── Parent resize tracking ─────────────────────────────────────────────────

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # type: ignore[override]
        if obj is self.parent() and event.type() == QEvent.Type.Resize:
            self._reposition()
        return super().eventFilter(obj, event)

    def _reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        margin = self.MARGIN
        x = margin
        y = parent.height() - self.height() - margin
        self.move(x, max(margin, y))

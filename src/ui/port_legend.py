from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QLabel,
    QWidget,
)

from core.io_data import IoDataType
from ui.theme import (
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
    """Tiny coloured circle that mirrors a single-type port's appearance.

    Painted (rather than CSS-styled) so the legend swatch and the port
    dot use exactly the same shape — a darker fill ringed by the full
    type colour — keeping the visual story consistent. See
    :class:`ui.port_item.PortItem` for the matching port-side rendering.
    """

    SIZE: int = 12
    _RING_WIDTH: float = 1.4
    _FILL_DARKEN: int = 200

    def __init__(self, color: QColor, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = color
        self.setFixedSize(self.SIZE, self.SIZE)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # Inset the rect by half the pen width so the ring sits inside
        # the widget bounds and isn't clipped on either side.
        inset = self._RING_WIDTH / 2
        rect = QRectF(inset, inset, self.SIZE - 2 * inset, self.SIZE - 2 * inset)
        painter.setPen(QPen(Qt.PenStyle.NoPen))
        painter.setBrush(QBrush(self._color.darker(self._FILL_DARKEN)))
        painter.drawEllipse(rect)
        painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        painter.setPen(QPen(self._color, self._RING_WIDTH))
        painter.drawEllipse(rect)


class PortLegend(QFrame):
    """Floating legend listing port colour → :class:`IoDataType` mappings.

    Mounted on the :class:`~ui.flow_view.FlowView` viewport and anchored
    to its bottom-left corner. Tracks viewport resizes through an
    event filter so the legend stays glued to the corner without the
    enclosing layout having to manage it.

    Stateless and read-only — the palette is taken from
    :data:`ui.theme.PORT_TYPE_COLORS` at construction time. Adding a
    new :class:`IoDataType` shows up here automatically as long as the
    new entry is also present in :data:`_TYPE_LABELS`; otherwise the
    legend falls back to the enum's display name.
    """

    MARGIN: int = 12
    OPACITY: float = 0.85

    _STYLE: str = """
        QFrame#PortLegend {
            background: #1f1f22;
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
    """

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("PortLegend")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        # Pass mouse events through to the canvas so the legend doesn't
        # eat clicks meant for nodes/links sitting underneath it.
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        opacity = QGraphicsOpacityEffect(self)
        opacity.setOpacity(self.OPACITY)
        self.setGraphicsEffect(opacity)
        self.setStyleSheet(self._STYLE)

        layout = QGridLayout(self)
        layout.setContentsMargins(10, 8, 12, 8)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(4)

        title = QLabel("Port types")
        title.setObjectName("PortLegendTitle")
        # Span both columns so the title sits above swatch + label.
        layout.addWidget(title, 0, 0, 1, 2)

        for row, t in enumerate(IoDataType, start=1):
            color = PORT_TYPE_COLORS.get(t, PORT_TYPE_DEFAULT_COLOR)
            label = QLabel(_TYPE_LABELS.get(t, t.value))
            label.setProperty("class", "PortLegendItem")
            layout.addWidget(_Swatch(color, self), row, 0)
            layout.addWidget(label, row, 1)

        self.adjustSize()
        parent.installEventFilter(self)
        self._reposition()

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

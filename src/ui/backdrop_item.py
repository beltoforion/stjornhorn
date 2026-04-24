from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QGraphicsItem

from ui.theme import NODE_BORDER_SELECTED

if TYPE_CHECKING:
    pass


#: Default fill when a backdrop is first dropped — a subtle, muted
#: amber so the frame reads as a loose grouping affordance without
#: fighting the nodes inside for attention.
DEFAULT_BACKDROP_COLOR: QColor = QColor(70, 60, 40, 140)

#: Default dimensions used when the user drops a fresh backdrop.
DEFAULT_BACKDROP_WIDTH: float = 320.0
DEFAULT_BACKDROP_HEIGHT: float = 220.0

#: Minimum size when the user drags the resize grip. Small enough that
#: a backdrop can frame a single node, but not so small it collapses
#: into an invisible square.
MIN_BACKDROP_WIDTH: float = 80.0
MIN_BACKDROP_HEIGHT: float = 60.0

#: Built-in palette offered through the context menu. Kept deliberately
#: small — this is a "hint at intent" affordance, not a full colour
#: picker. Values mirror the muted dark-theme palette so backdrops
#: read as loose grouping rather than as primary UI.
BACKDROP_PRESETS: dict[str, QColor] = {
    "Amber":   QColor( 70,  60,  40, 140),
    "Azure":   QColor( 40,  60,  80, 140),
    "Forest":  QColor( 40,  70,  50, 140),
    "Plum":    QColor( 70,  45,  70, 140),
    "Slate":   QColor( 55,  55,  60, 140),
}


class BackdropItem(QGraphicsItem):
    """Rectangular frame drawn behind a group of nodes.

    A backdrop is a pure visual affordance: it has no connection to
    the flow model, no execution semantics, and does not appear in the
    node palette. Use it as a "chapter heading" on the canvas —
    e.g. "Colour prep", "Alpha mask" — so dense pipelines stay
    readable.

    Sits on a lower Z than nodes (:attr:`Z_VALUE`) so mouse events on
    the interior of a framed group still reach the node on top. Drag
    the title to move the backdrop; drag the bottom-right grip to
    resize.
    """

    Z_VALUE: int = -10
    HEADER_HEIGHT: float = 22.0
    CORNER_RADIUS: float = 6.0
    RESIZE_GRIP_SIZE: float = 12.0
    TITLE_PADDING: float = 8.0

    def __init__(
        self,
        title: str = "Backdrop",
        width: float = DEFAULT_BACKDROP_WIDTH,
        height: float = DEFAULT_BACKDROP_HEIGHT,
        color: QColor | None = None,
    ) -> None:
        super().__init__()
        self._title: str = title
        self._width: float = float(width)
        self._height: float = float(height)
        self._color: QColor = QColor(color if color is not None else DEFAULT_BACKDROP_COLOR)

        self.setZValue(self.Z_VALUE)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemSendsScenePositionChanges, True,
        )

        self._resize_grip = _BackdropResizeGrip(self)
        self._position_resize_grip()

    # ── Public API ─────────────────────────────────────────────────────────────

    @property
    def title(self) -> str:
        return self._title

    def set_title(self, title: str) -> None:
        self._title = str(title)
        self.update()

    @property
    def color(self) -> QColor:
        return QColor(self._color)

    def set_color(self, color: QColor) -> None:
        self._color = QColor(color)
        self.update()

    @property
    def width(self) -> float:
        return self._width

    @property
    def height(self) -> float:
        return self._height

    def set_size(self, width: float, height: float) -> None:
        """Update the backdrop rectangle. Enforces the minimum so the
        resize grip can't collapse the frame out of existence."""
        new_w = max(MIN_BACKDROP_WIDTH, float(width))
        new_h = max(MIN_BACKDROP_HEIGHT, float(height))
        if (new_w, new_h) == (self._width, self._height):
            return
        self.prepareGeometryChange()
        self._width = new_w
        self._height = new_h
        self._position_resize_grip()
        self.update()

    # ── Qt overrides ───────────────────────────────────────────────────────────

    def boundingRect(self) -> QRectF:  # type: ignore[override]
        return QRectF(0, 0, self._width, self._height)

    def paint(self, painter: QPainter, option, widget=None) -> None:  # type: ignore[override]
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Body
        body_path = QPainterPath()
        body_path.addRoundedRect(
            self.boundingRect(), self.CORNER_RADIUS, self.CORNER_RADIUS,
        )
        painter.fillPath(body_path, QBrush(self._color))

        # Border: amber when selected, subtle darker tint otherwise.
        if self.isSelected():
            painter.setPen(QPen(NODE_BORDER_SELECTED, 1.5))
        else:
            border = QColor(self._color)
            border.setAlpha(230)
            border.setRed(max(0, border.red() - 25))
            border.setGreen(max(0, border.green() - 25))
            border.setBlue(max(0, border.blue() - 25))
            painter.setPen(QPen(border, 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(body_path)

        # Title bar text — rendered directly onto the header strip.
        if self._title:
            title_rect = QRectF(
                self.TITLE_PADDING,
                0.0,
                self._width - 2 * self.TITLE_PADDING,
                self.HEADER_HEIGHT,
            )
            font = QFont(painter.font())
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor(230, 230, 230))
            painter.drawText(
                title_rect,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                self._title,
            )

    # ── Internals ──────────────────────────────────────────────────────────────

    def _position_resize_grip(self) -> None:
        self._resize_grip.setPos(
            self._width - self.RESIZE_GRIP_SIZE,
            self._height - self.RESIZE_GRIP_SIZE,
        )


class _BackdropResizeGrip(QGraphicsItem):
    """Bottom-right drag handle that resizes its owning backdrop."""

    SIZE: float = 12.0

    def __init__(self, backdrop: BackdropItem) -> None:
        super().__init__(parent=backdrop)
        self._backdrop = backdrop
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemStacksBehindParent, False)
        self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        self.setZValue(1)
        self._drag_start_scene: QPointF | None = None
        self._drag_start_size: tuple[float, float] | None = None

    def boundingRect(self) -> QRectF:  # type: ignore[override]
        return QRectF(0, 0, self.SIZE, self.SIZE)

    def paint(self, painter: QPainter, option, widget=None) -> None:  # type: ignore[override]
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor(200, 200, 200, 180), 1))
        # Three short diagonal tick marks — enough to telegraph
        # "resize handle" without looking like a button.
        for i in (2, 5, 8):
            painter.drawLine(
                QPointF(self.SIZE - i, self.SIZE - 1),
                QPointF(self.SIZE - 1, self.SIZE - i),
            )

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_scene = event.scenePos()
            self._drag_start_size = (self._backdrop.width, self._backdrop.height)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._drag_start_scene is not None and self._drag_start_size is not None:
            delta = event.scenePos() - self._drag_start_scene
            w0, h0 = self._drag_start_size
            self._backdrop.set_size(w0 + delta.x(), h0 + delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        self._drag_start_scene = None
        self._drag_start_size = None
        super().mouseReleaseEvent(event)

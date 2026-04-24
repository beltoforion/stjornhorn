from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QGraphicsItem

from ui.icons import material_icon
from ui.theme import NODE_BORDER_SELECTED, NODE_TITLE_TEXT_COLOR

if TYPE_CHECKING:
    pass


#: Default fill when a backdrop is first dropped — a subtle, muted
#: amber so the frame reads as a loose grouping affordance without
#: fighting the nodes inside for attention.
DEFAULT_BACKDROP_COLOR: QColor = QColor(70, 60, 40, 140)

#: Default dimensions used when the user drops a fresh backdrop.
DEFAULT_BACKDROP_WIDTH: float = 320.0
DEFAULT_BACKDROP_HEIGHT: float = 220.0

#: Minimum size when the user drags any of the resize grips. Small
#: enough that a backdrop can frame a single node, but not so small
#: it collapses into an invisible square.
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


class _Corner(Enum):
    """Identifier for which corner of a backdrop a resize grip is attached to.

    The mapping is consistent with screen coordinates used by Qt:
    Y grows downward, so "north" is the top edge and "south" the
    bottom.
    """
    NW = "NW"
    NE = "NE"
    SW = "SW"
    SE = "SE"


class BackdropItem(QGraphicsItem):
    """Rectangular frame drawn behind a group of nodes.

    A backdrop is a pure visual affordance: it has no connection to
    the flow model, no execution semantics, and does not appear in the
    node palette. Use it as a "chapter heading" on the canvas —
    e.g. "Colour prep", "Alpha mask" — so dense pipelines stay
    readable.

    Sits on a lower Z than nodes (:attr:`Z_VALUE`) so mouse events on
    the interior of a framed group still reach the node on top. Drag
    the title bar to move; drag *any* of the four corner grips to
    resize — both axes scale at once and the opposite corner stays
    pinned. All four are needed because the bottom-right grip alone
    is unreachable as soon as another node sits on top of it.

    The header carries an X close button on the right edge, mirroring
    the affordance every regular node has.
    """

    Z_VALUE: int = -10
    HEADER_HEIGHT: float = 22.0
    CORNER_RADIUS: float = 6.0
    GRIP_SIZE: float = 12.0
    CLOSE_BUTTON_SIZE: float = 14.0
    CAPTURE_BUTTON_SIZE: float = 14.0
    HEADER_BUTTON_GAP: float = 4.0
    HEADER_BUTTON_MARGIN: float = 4.0
    TITLE_PADDING: float = 8.0

    def __init__(
        self,
        title: str = "Backdrop",
        width: float = DEFAULT_BACKDROP_WIDTH,
        height: float = DEFAULT_BACKDROP_HEIGHT,
        color: QColor | None = None,
        capture_active: bool = False,
    ) -> None:
        super().__init__()
        self._title: str = title
        self._width: float = float(width)
        self._height: float = float(height)
        self._color: QColor = QColor(color if color is not None else DEFAULT_BACKDROP_COLOR)
        self._capture_active: bool = bool(capture_active)
        # Drag bookkeeping: when capture is on and the user starts
        # dragging the backdrop, we snapshot every node fully inside
        # the frame at press-time and shift them by the same delta on
        # every position change. The snapshot is *not* re-evaluated
        # mid-drag, so a node that wasn't framed at press-time won't
        # be swept along just because the moving backdrop crossed it.
        self._captured_snapshot: list = []
        self._drag_anchor_pos: QPointF | None = None

        self.setZValue(self.Z_VALUE)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemSendsScenePositionChanges, True,
        )

        # One grip per corner — bottom-right alone gets buried under
        # nodes too easily to be a reliable handle.
        self._grips: dict[_Corner, _BackdropResizeGrip] = {
            corner: _BackdropResizeGrip(self, corner) for corner in _Corner
        }
        self._close_button = _BackdropCloseButton(self)
        self._capture_button = _BackdropCaptureButton(self)
        self._reposition_children()

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

    @property
    def capture_active(self) -> bool:
        """True if dragging the backdrop should sweep enclosed nodes along.

        See :meth:`set_capture_active`. Reflects the toggle button in
        the header.
        """
        return self._capture_active

    def set_capture_active(self, active: bool) -> None:
        flag = bool(active)
        if flag == self._capture_active:
            return
        self._capture_active = flag
        self._capture_button.update()

    def set_size(self, width: float, height: float) -> None:
        """Update the backdrop rectangle. Enforces the minimum so the
        resize grips can't collapse the frame out of existence."""
        new_w = max(MIN_BACKDROP_WIDTH, float(width))
        new_h = max(MIN_BACKDROP_HEIGHT, float(height))
        if (new_w, new_h) == (self._width, self._height):
            return
        self.prepareGeometryChange()
        self._width = new_w
        self._height = new_h
        self._reposition_children()
        self.update()

    # ── Capture / drag-with-contents ───────────────────────────────────────────

    def captured_node_items(self) -> list:
        """Return every node-item *fully* enclosed by this backdrop.

        "Fully enclosed" means the node's scene-bounding rect is
        completely inside the backdrop's scene-bounding rect — partial
        overlap doesn't count, so a node only "joins" the backdrop's
        group once the user has clearly placed it inside.

        Imported lazily to avoid pulling :mod:`ui.node_item` (which
        wires up Qt widgets and the param-widget infrastructure) into
        backdrop tests that only care about geometry.
        """
        if self.scene() is None:
            return []
        from ui.node_item import NodeItem

        backdrop_rect = self.sceneBoundingRect()
        captured = []
        for item in self.scene().items():
            if isinstance(item, NodeItem) and backdrop_rect.contains(
                item.sceneBoundingRect()
            ):
                captured.append(item)
        return captured

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        # When capture is on, snapshot the framed nodes + their
        # current positions so the move handler can shift them by the
        # same delta the backdrop travels. The snapshot is taken
        # *before* super() starts the drag so press-time geometry is
        # what we lock in.
        if self._capture_active and event.button() == Qt.MouseButton.LeftButton:
            self._drag_anchor_pos = self.scenePos()
            self._captured_snapshot = [
                (item, item.pos()) for item in self.captured_node_items()
            ]
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        self._drag_anchor_pos = None
        self._captured_snapshot = []
        super().mouseReleaseEvent(event)

    def itemChange(self, change, value):  # type: ignore[override]
        if (
            change == QGraphicsItem.GraphicsItemChange.ItemScenePositionHasChanged
            and self._drag_anchor_pos is not None
            and self._captured_snapshot
        ):
            delta = self.scenePos() - self._drag_anchor_pos
            for node_item, start_pos in self._captured_snapshot:
                node_item.setPos(start_pos + delta)
        return super().itemChange(change, value)

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
        # Each header button paints itself separately so the text doesn't
        # need to know about them; we just leave room on the right for
        # both (capture toggle + close).
        if self._title:
            title_rect = QRectF(
                self.TITLE_PADDING,
                0.0,
                self._width
                - 2 * self.TITLE_PADDING
                - self.CLOSE_BUTTON_SIZE
                - self.HEADER_BUTTON_GAP
                - self.CAPTURE_BUTTON_SIZE
                - self.HEADER_BUTTON_MARGIN,
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

    def _reposition_children(self) -> None:
        """Place every grip + header button at its corner / header slot.

        Called from :meth:`set_size` and from ``__init__``. Each grip
        sits exactly on its corner (top-left coordinate of the
        ``GRIP_SIZE`` square aligns with the corner so the grip extends
        into the frame and not outside it).
        """
        gs = self.GRIP_SIZE
        w = self._width
        h = self._height
        self._grips[_Corner.NW].setPos(0, 0)
        self._grips[_Corner.NE].setPos(w - gs, 0)
        self._grips[_Corner.SW].setPos(0, h - gs)
        self._grips[_Corner.SE].setPos(w - gs, h - gs)

        cb_size = self.CLOSE_BUTTON_SIZE
        cap_size = self.CAPTURE_BUTTON_SIZE
        margin = self.HEADER_BUTTON_MARGIN
        gap = self.HEADER_BUTTON_GAP
        # Right-aligned button row: [Capture] [gap] [Close] [margin] | edge
        close_x = w - cb_size - margin
        capture_x = close_x - gap - cap_size
        self._close_button.setPos(close_x, (self.HEADER_HEIGHT - cb_size) / 2.0)
        self._capture_button.setPos(capture_x, (self.HEADER_HEIGHT - cap_size) / 2.0)


class _BackdropResizeGrip(QGraphicsItem):
    """Drag handle attached to one corner of a backdrop.

    Each corner pins the *opposite* corner during a drag, so the
    handle the user grabs is the one that follows the cursor and the
    frame grows / shrinks symmetrically about that anchor. Below the
    minimum size, the frame clamps and the dragged corner stops where
    it would have shrunk past the anchor.
    """

    SIZE: float = 12.0

    _CURSORS: dict[_Corner, Qt.CursorShape] = {
        _Corner.NW: Qt.CursorShape.SizeFDiagCursor,  # top-left  ↘ shape
        _Corner.SE: Qt.CursorShape.SizeFDiagCursor,  # bot-right ↘
        _Corner.NE: Qt.CursorShape.SizeBDiagCursor,  # top-right ↙
        _Corner.SW: Qt.CursorShape.SizeBDiagCursor,  # bot-left  ↙
    }

    def __init__(self, backdrop: BackdropItem, corner: _Corner) -> None:
        super().__init__(parent=backdrop)
        self._backdrop = backdrop
        self._corner = corner
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemStacksBehindParent, False)
        self.setCursor(self._CURSORS[corner])
        self.setZValue(1)
        self._drag_start_scene: QPointF | None = None
        self._drag_start_pos: QPointF | None = None
        self._drag_start_size: tuple[float, float] | None = None

    def boundingRect(self) -> QRectF:  # type: ignore[override]
        return QRectF(0, 0, self.SIZE, self.SIZE)

    def paint(self, painter: QPainter, option, widget=None) -> None:  # type: ignore[override]
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor(200, 200, 200, 180), 1))
        # Three short diagonal tick marks oriented for the corner the
        # grip sits on, so the affordance points "outward" the way an
        # actual resize handle should.
        s = self.SIZE
        if self._corner == _Corner.SE:
            for i in (2, 5, 8):
                painter.drawLine(QPointF(s - i, s - 1), QPointF(s - 1, s - i))
        elif self._corner == _Corner.NW:
            for i in (2, 5, 8):
                painter.drawLine(QPointF(0, i), QPointF(i, 0))
        elif self._corner == _Corner.NE:
            for i in (2, 5, 8):
                painter.drawLine(QPointF(s - i, 0), QPointF(s, i))
        else:  # SW
            for i in (2, 5, 8):
                painter.drawLine(QPointF(0, s - i), QPointF(i, s))

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_scene = event.scenePos()
            self._drag_start_pos = self._backdrop.pos()
            self._drag_start_size = (self._backdrop.width, self._backdrop.height)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if (
            self._drag_start_scene is None
            or self._drag_start_pos is None
            or self._drag_start_size is None
        ):
            super().mouseMoveEvent(event)
            return
        delta = event.scenePos() - self._drag_start_scene
        sp = self._drag_start_pos
        sw, sh = self._drag_start_size

        new_x = sp.x()
        new_y = sp.y()
        new_w = sw
        new_h = sh

        if self._corner in (_Corner.SE, _Corner.NE):
            new_w = sw + delta.x()
        else:  # NW, SW — pull the left edge with the cursor
            new_w = sw - delta.x()
            new_x = sp.x() + delta.x()

        if self._corner in (_Corner.SE, _Corner.SW):
            new_h = sh + delta.y()
        else:  # NW, NE — pull the top edge with the cursor
            new_h = sh - delta.y()
            new_y = sp.y() + delta.y()

        # Clamp to minimum, and when clamped, re-pin the moved edge so
        # the opposite corner doesn't drift.
        if new_w < MIN_BACKDROP_WIDTH:
            if self._corner in (_Corner.NW, _Corner.SW):
                new_x = sp.x() + (sw - MIN_BACKDROP_WIDTH)
            new_w = MIN_BACKDROP_WIDTH
        if new_h < MIN_BACKDROP_HEIGHT:
            if self._corner in (_Corner.NW, _Corner.NE):
                new_y = sp.y() + (sh - MIN_BACKDROP_HEIGHT)
            new_h = MIN_BACKDROP_HEIGHT

        self._backdrop.setPos(new_x, new_y)
        self._backdrop.set_size(new_w, new_h)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        self._drag_start_scene = None
        self._drag_start_pos = None
        self._drag_start_size = None
        super().mouseReleaseEvent(event)


class _BackdropCaptureButton(QGraphicsItem):
    """Toggle button that switches the backdrop's "capture" mode on/off.

    While capture is active, dragging the backdrop sweeps every fully-
    enclosed node along by the same delta. The button paints a small
    push-pin glyph (Material Icons) and shows a faint white wash when
    hovered, plus a stronger wash when the toggle is on — same visual
    grammar as :class:`~ui.node_item._SkipButtonItem`.
    """

    SIZE: float = 14.0
    Z_VALUE: int = 2

    def __init__(self, backdrop: BackdropItem) -> None:
        super().__init__(parent=backdrop)
        self._backdrop = backdrop
        self._hovered = False
        self._pressed = False
        self.setZValue(self.Z_VALUE)
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setToolTip(
            "Capture nodes — drag the backdrop and any fully enclosed "
            "node moves with it."
        )
        # Cache the icon — the same QIcon paints at every state, so
        # re-creating it on each frame would waste font-rendering work.
        self._icon = material_icon("push_pin", color=NODE_TITLE_TEXT_COLOR)

    def boundingRect(self) -> QRectF:  # type: ignore[override]
        return QRectF(0, 0, self.SIZE, self.SIZE)

    def paint(self, painter: QPainter, option, widget=None) -> None:  # type: ignore[override]
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        active = self._backdrop.capture_active
        if self._hovered or self._pressed or active:
            painter.setPen(Qt.NoPen)
            alpha = 120 if active else 70
            painter.setBrush(QBrush(QColor(255, 255, 255, alpha)))
            painter.drawRoundedRect(self.boundingRect(), 2, 2)

        # Push-pin glyph rendered through the Material Icons font so
        # it scales crisply alongside the close X.
        size = int(self.SIZE)
        pixmap = self._icon.pixmap(QSize(size, size))
        painter.drawPixmap(0, 0, pixmap)

    def hoverEnterEvent(self, event) -> None:  # type: ignore[override]
        self._hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:  # type: ignore[override]
        self._hovered = False
        self.update()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton and self._pressed:
            self._pressed = False
            if self.boundingRect().contains(event.pos()):
                self._backdrop.set_capture_active(
                    not self._backdrop.capture_active
                )
            self.update()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class _BackdropCloseButton(QGraphicsItem):
    """``X`` button at the top-right of a backdrop's header.

    Clicking it asks the owning scene to remove the backdrop, mirroring
    the close affordance every regular node header carries.
    """

    SIZE: float = 14.0
    Z_VALUE: int = 2

    def __init__(self, backdrop: BackdropItem) -> None:
        super().__init__(parent=backdrop)
        self._backdrop = backdrop
        self._hovered = False
        self._pressed = False
        self.setZValue(self.Z_VALUE)
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def boundingRect(self) -> QRectF:  # type: ignore[override]
        return QRectF(0, 0, self.SIZE, self.SIZE)

    def paint(self, painter: QPainter, option, widget=None) -> None:  # type: ignore[override]
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self._hovered or self._pressed:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(255, 255, 255, 70)))
            painter.drawRoundedRect(self.boundingRect(), 2, 2)
        pen = QPen(NODE_TITLE_TEXT_COLOR, 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        m = 4.0
        s = self.SIZE
        painter.drawLine(QPointF(m, m), QPointF(s - m, s - m))
        painter.drawLine(QPointF(s - m, m), QPointF(m, s - m))

    def hoverEnterEvent(self, event) -> None:  # type: ignore[override]
        self._hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:  # type: ignore[override]
        self._hovered = False
        self.update()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton and self._pressed:
            self._pressed = False
            self.update()
            if self.boundingRect().contains(event.pos()):
                scene = self.scene()
                backdrop = self._backdrop
                if scene is not None and hasattr(scene, "remove_backdrop"):
                    # Defer so we don't delete ourselves from inside
                    # our own event handler.
                    QTimer.singleShot(0, lambda: scene.remove_backdrop(backdrop))
            event.accept()
            return
        super().mouseReleaseEvent(event)

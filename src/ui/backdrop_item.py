from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QGraphicsItem


#: Layout of the eight resize grips around a backdrop. ``dx`` / ``dy``
#: are the direction multipliers for the edge each grip controls:
#: ``-1`` = left / top edge, ``+1`` = right / bottom edge, ``0`` =
#: that axis is not affected by this grip. The ``cursor`` is the Qt
#: shape shown while hovering / dragging the grip.
_GRIP_LAYOUT: tuple[tuple[str, int, int, Qt.CursorShape], ...] = (
    ("nw", -1, -1, Qt.CursorShape.SizeFDiagCursor),
    ("n",   0, -1, Qt.CursorShape.SizeVerCursor),
    ("ne", +1, -1, Qt.CursorShape.SizeBDiagCursor),
    ("w",  -1,  0, Qt.CursorShape.SizeHorCursor),
    ("e",  +1,  0, Qt.CursorShape.SizeHorCursor),
    ("sw", -1, +1, Qt.CursorShape.SizeBDiagCursor),
    ("s",   0, +1, Qt.CursorShape.SizeVerCursor),
    ("se", +1, +1, Qt.CursorShape.SizeFDiagCursor),
)

#: Edge length of a square resize grip, in scene units. Small enough
#: that the eight grips don't visually crowd the frame, large enough
#: to be a comfortable click target.
_GRIP_SIZE: float = 8.0

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


class BackdropItem(QGraphicsItem):
    """Rectangular frame drawn behind a group of nodes.

    A backdrop is a pure visual affordance: it has no connection to
    the flow model, no execution semantics, and does not appear in
    the node palette. Use it as a "chapter heading" on the canvas —
    e.g. "Colour prep", "Alpha mask" — so dense pipelines stay
    readable.

    Sits on a lower Z than nodes (:attr:`Z_VALUE`) so mouse events
    on the interior of a framed group still reach the node on top.
    Drag the title bar to move. Eight resize grips (four corners,
    four edge midpoints) appear when the backdrop is hovered or
    selected; dragging any grip resizes the rectangle, with the
    opposite corner / edge anchored. Resizing only changes the
    frame's geometry — it never moves the framed nodes (those move
    only when the user drags the body, not a grip).

    The header carries an X close button on the right edge, mirroring
    the affordance every regular node has.
    """

    Z_VALUE: int = -10
    HEADER_HEIGHT: float = 22.0
    CORNER_RADIUS: float = 6.0
    CLOSE_BUTTON_SIZE: float = 14.0
    HEADER_BUTTON_MARGIN: float = 4.0
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
        # Drag bookkeeping: when the user starts dragging the
        # backdrop, we snapshot every node fully inside the frame at
        # press-time and shift them by the same delta on every
        # position change. The snapshot is *not* re-evaluated
        # mid-drag, so a node that wasn't framed at press-time won't
        # be swept along just because the moving backdrop crossed it.
        # Capture-the-enclosed is always on — the typical creation
        # path is "Create Group" around an existing selection, so by
        # the time the user moves the backdrop, it already frames
        # exactly what they want to drag together.
        self._captured_snapshot: list = []
        self._drag_anchor_pos: QPointF | None = None
        # Reveal-state for the resize grips. Qt routes hover to the
        # topmost item under the cursor, so the body and the grips
        # never both report ``hovered=True`` at the same time —
        # tracking each separately keeps the grips visible while
        # the cursor crosses from body to grip and back.
        self._body_hovered: bool = False
        self._grip_hover_count: int = 0

        self.setZValue(self.Z_VALUE)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemSendsScenePositionChanges, True,
        )
        # Hover events drive the reveal of the resize grips. Without
        # this flag, hoverEnter/Leave never fire and the grips would
        # only show on selection.
        self.setAcceptHoverEvents(True)

        self._close_button = _BackdropCloseButton(self)
        self._grips: list[_BackdropResizeGrip] = [
            _BackdropResizeGrip(self, name, dx, dy, cursor)
            for name, dx, dy, cursor in _GRIP_LAYOUT
        ]
        # Grips stay invisible until the backdrop is hovered / selected;
        # they shouldn't compete with the chrome of framed nodes.
        for grip in self._grips:
            grip.setVisible(False)
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

    def set_size(self, width: float, height: float) -> None:
        """Update the backdrop rectangle.

        Called by the loader, :meth:`FlowScene.create_group_around_selection`,
        and the interactive resize grips. ``width`` / ``height`` are
        clamped at :data:`MIN_BACKDROP_WIDTH` / :data:`MIN_BACKDROP_HEIGHT`
        so a grip dragged past the minimum stops the rectangle from
        collapsing into an unclickable sliver.
        """
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
        # Snapshot the framed nodes + their current positions so the
        # move handler can shift them by the same delta the backdrop
        # travels. Taken *before* super() starts the drag so
        # press-time geometry is what we lock in.
        if event.button() == Qt.MouseButton.LeftButton:
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
        elif change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self._refresh_grip_visibility()
        return super().itemChange(change, value)

    # ── Hover-driven grip reveal ───────────────────────────────────────────────

    def hoverEnterEvent(self, event) -> None:  # type: ignore[override]
        self._body_hovered = True
        self._refresh_grip_visibility()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:  # type: ignore[override]
        self._body_hovered = False
        self._refresh_grip_visibility()
        super().hoverLeaveEvent(event)

    def _on_grip_hover_changed(self, entering: bool) -> None:
        """Bumped by each child grip on hoverEnter / hoverLeave so the
        grips stay visible while the cursor crosses from the body
        onto a grip."""
        if entering:
            self._grip_hover_count += 1
        elif self._grip_hover_count > 0:
            self._grip_hover_count -= 1
        self._refresh_grip_visibility()

    def _refresh_grip_visibility(self) -> None:
        visible = (
            self._body_hovered
            or self._grip_hover_count > 0
            or self.isSelected()
        )
        for grip in self._grips:
            grip.setVisible(visible)

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
        # The close button paints itself separately, so we just leave
        # room on the right for it.
        if self._title:
            title_rect = QRectF(
                self.TITLE_PADDING,
                0.0,
                self._width
                - 2 * self.TITLE_PADDING
                - self.CLOSE_BUTTON_SIZE
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
        """Place the close button in its header slot and the eight
        resize grips at the corners and edge midpoints.

        Called from :meth:`set_size` and from ``__init__``.
        """
        cb_size = self.CLOSE_BUTTON_SIZE
        margin = self.HEADER_BUTTON_MARGIN
        self._close_button.setPos(
            self._width - cb_size - margin,
            (self.HEADER_HEIGHT - cb_size) / 2.0,
        )

        if not getattr(self, "_grips", None):
            return
        gs = _GRIP_SIZE
        half = gs / 2.0
        w = self._width
        h = self._height
        # Top-left corner of each grip in local coords. Grips sit
        # fully inside the backdrop's body so the cursor crosses the
        # body first on its way to a grip — that way the backdrop's
        # hoverEnter fires and the grips become visible *before* the
        # user reaches them.
        positions = {
            "nw": (0,            0),
            "n":  (w / 2 - half, 0),
            "ne": (w - gs,       0),
            "w":  (0,            h / 2 - half),
            "e":  (w - gs,       h / 2 - half),
            "sw": (0,            h - gs),
            "s":  (w / 2 - half, h - gs),
            "se": (w - gs,       h - gs),
        }
        for grip in self._grips:
            x, y = positions[grip.name]
            grip.setPos(x, y)


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


class _BackdropResizeGrip(QGraphicsItem):
    """Square resize handle anchored to one edge or corner of a
    :class:`BackdropItem`.

    The grip lives as a child of the backdrop, drawn in local coords
    so :meth:`BackdropItem._reposition_children` can place it without
    any scene-coord arithmetic. ``dx`` and ``dy`` are direction
    multipliers for the edge this grip controls — ``-1`` means the
    grip drives the left / top edge (so the right / bottom stays
    anchored), ``+1`` the opposite, ``0`` means that axis is
    untouched. The four-corner grips have both axes non-zero, the
    four edge-midpoint grips have exactly one axis zero.

    Resize math runs in scene coords, snapshotted at press-time, so
    the grip's own per-frame position update during the drag never
    feeds back into the cursor delta.
    """

    Z_VALUE: int = 1

    def __init__(
        self,
        backdrop: BackdropItem,
        name: str,
        dx: int,
        dy: int,
        cursor: Qt.CursorShape,
    ) -> None:
        super().__init__(parent=backdrop)
        self._backdrop = backdrop
        self.name: str = name
        self._dx: int = dx
        self._dy: int = dy
        self._press_scene_pos: QPointF | None = None
        self._press_backdrop_pos: QPointF | None = None
        self._press_width: float = 0.0
        self._press_height: float = 0.0
        self._dirty_during_drag: bool = False

        self.setZValue(self.Z_VALUE)
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setCursor(cursor)

    def boundingRect(self) -> QRectF:  # type: ignore[override]
        return QRectF(0, 0, _GRIP_SIZE, _GRIP_SIZE)

    def paint(self, painter: QPainter, option, widget=None) -> None:  # type: ignore[override]
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(NODE_BORDER_SELECTED, 1.0))
        painter.setBrush(QBrush(QColor(40, 40, 40, 220)))
        painter.drawRect(self.boundingRect().adjusted(0.5, 0.5, -0.5, -0.5))

    def hoverEnterEvent(self, event) -> None:  # type: ignore[override]
        self._backdrop._on_grip_hover_changed(entering=True)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:  # type: ignore[override]
        self._backdrop._on_grip_hover_changed(entering=False)
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        # Snapshot scene-coord state so per-frame updates compute the
        # cursor delta against a fixed reference, not against the
        # grip's own moving position.
        self._press_scene_pos = event.scenePos()
        self._press_backdrop_pos = QPointF(self._backdrop.pos())
        self._press_width = self._backdrop.width
        self._press_height = self._backdrop.height
        self._dirty_during_drag = False
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._press_scene_pos is None:
            super().mouseMoveEvent(event)
            return
        delta = event.scenePos() - self._press_scene_pos
        self._apply_resize(delta.x(), delta.y())
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if event.button() != Qt.MouseButton.LeftButton or self._press_scene_pos is None:
            super().mouseReleaseEvent(event)
            return
        if self._dirty_during_drag:
            scene = self._backdrop.scene()
            if scene is not None and hasattr(scene, "mark_dirty"):
                scene.mark_dirty()
        self._press_scene_pos = None
        self._press_backdrop_pos = None
        self._press_width = 0.0
        self._press_height = 0.0
        self._dirty_during_drag = False
        event.accept()

    def _apply_resize(self, scene_dx: float, scene_dy: float) -> None:
        """Compute the new backdrop geometry from a scene-coord delta
        and push it through :meth:`BackdropItem.set_size` (plus a
        ``setPos`` for grips that move the top / left edge).

        Clamping happens before the position adjustment so that
        dragging past the minimum holds the anchored corner truly
        fixed instead of letting it drift.
        """
        assert self._press_backdrop_pos is not None
        dx = self._dx
        dy = self._dy

        if dx == +1:
            new_w = max(MIN_BACKDROP_WIDTH, self._press_width + scene_dx)
            pos_dx = 0.0
        elif dx == -1:
            new_w = max(MIN_BACKDROP_WIDTH, self._press_width - scene_dx)
            # Effective left-edge shift: identical to scene_dx until we
            # hit the minimum, then pinned so the right edge stays put.
            pos_dx = self._press_width - new_w
        else:
            new_w = self._press_width
            pos_dx = 0.0

        if dy == +1:
            new_h = max(MIN_BACKDROP_HEIGHT, self._press_height + scene_dy)
            pos_dy = 0.0
        elif dy == -1:
            new_h = max(MIN_BACKDROP_HEIGHT, self._press_height - scene_dy)
            pos_dy = self._press_height - new_h
        else:
            new_h = self._press_height
            pos_dy = 0.0

        new_pos = QPointF(
            self._press_backdrop_pos.x() + pos_dx,
            self._press_backdrop_pos.y() + pos_dy,
        )
        if new_pos != self._backdrop.pos():
            self._backdrop.setPos(new_pos)
            self._dirty_during_drag = True
        if (new_w, new_h) != (self._backdrop.width, self._backdrop.height):
            self._backdrop.set_size(new_w, new_h)
            self._dirty_during_drag = True

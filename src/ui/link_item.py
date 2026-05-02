from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPathItem

from ui.theme import (
    LINK_COLOR,
    LINK_GLOW_STROKES,
    LINK_SELECTED_COLOR,
    LINK_STROKE_WIDTH,
)

#: Worst-case outer-glow extent in scene pixels around the wire
#: path. Sized to cover any registered theme's
#: ``Theme.LINK_GLOW_STROKES`` so ``boundingRect`` stays
#: theme-independent.
_LINK_BOUNDING_PAD: float = 6.0

if TYPE_CHECKING:
    from ui.port_item import PortItem


class LinkItem(QGraphicsPathItem):
    """Bezier connection between two :class:`PortItem` instances.

    The path is recomputed whenever either endpoint moves. Links sit just
    below nodes in the Z order so dragging over them doesn't obscure the
    ports.
    """

    Z_VALUE = -1

    def __init__(self, src_port: PortItem, dst_port: PortItem) -> None:
        super().__init__()
        self._src_port = src_port
        self._dst_port = dst_port
        self.setZValue(self.Z_VALUE)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setPen(QPen(LINK_COLOR, 2))
        self.setAcceptHoverEvents(False)
        src_port.add_link(self)
        dst_port.add_link(self)
        self.update_path()

    # ── Endpoints ──────────────────────────────────────────────────────────────

    @property
    def src_port(self) -> PortItem:
        return self._src_port

    @property
    def dst_port(self) -> PortItem:
        return self._dst_port

    # ── Path ───────────────────────────────────────────────────────────────────

    def update_path(self) -> None:
        """Recompute the bezier from src_port to dst_port."""
        src = self._src_port.scenePos()
        dst = self._dst_port.scenePos()
        self.setPath(_bezier_path(src, dst))

    def paint(self, painter, option, widget=None) -> None:  # type: ignore[override]
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        base_color = LINK_SELECTED_COLOR if self.isSelected() else LINK_COLOR
        path = self.path()
        # Themes opt into a wire halo via ``LINK_GLOW_STROKES``: each
        # entry is ``(stroke_width, alpha)`` and is painted before the
        # crisp inner stroke. Empty disables the halo entirely
        # (classic theme stays a single hairline).
        for width, alpha in LINK_GLOW_STROKES:
            glow = QColor(base_color)
            glow.setAlpha(alpha)
            pen = QPen(glow, width)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawPath(path)
        painter.setPen(QPen(base_color, LINK_STROKE_WIDTH))
        painter.drawPath(path)

    def boundingRect(self):  # type: ignore[override]
        # Padded by the worst-case glow extent across all registered
        # themes so the scene doesn't clip the halo during partial
        # repaints.
        return super().boundingRect().adjusted(
            -_LINK_BOUNDING_PAD, -_LINK_BOUNDING_PAD,
             _LINK_BOUNDING_PAD,  _LINK_BOUNDING_PAD,
        )

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def detach(self) -> None:
        """Unregister this link from both ports. Call before removing from
        the scene to prevent dangling references."""
        self._src_port.remove_link(self)
        self._dst_port.remove_link(self)


def _bezier_path(src: QPointF, dst: QPointF) -> QPainterPath:
    """Horizontal-tangent cubic bezier between two points.

    Good default look for left-to-right node editors: tangents always
    leave an output port rightward and enter an input port rightward.
    """
    path = QPainterPath(src)
    dx = max(60.0, abs(dst.x() - src.x()) * 0.5)
    ctrl1 = QPointF(src.x() + dx, src.y())
    ctrl2 = QPointF(dst.x() - dx, dst.y())
    path.cubicTo(ctrl1, ctrl2, dst)
    return path


class PendingLinkItem(QGraphicsPathItem):
    """Temporary link shown while the user is dragging a new connection."""

    Z_VALUE = -1

    def __init__(self, start: QPointF) -> None:
        super().__init__()
        self.setZValue(self.Z_VALUE)
        self.setPen(QPen(LINK_COLOR, 1, Qt.PenStyle.DashLine))
        self._start = start
        self._end = start
        self._rebuild()

    def update_end(self, end: QPointF) -> None:
        self._end = end
        self._rebuild()

    def _rebuild(self) -> None:
        self.setPath(_bezier_path(self._start, self._end))

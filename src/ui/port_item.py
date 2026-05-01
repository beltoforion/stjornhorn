from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsEllipseItem

from core.io_data import IoDataType
from ui.theme import (
    PORT_DIRECTION_GLYPH_COLOR,
    PORT_HOVER_COLOR,
    PORT_TYPE_COLORS,
    PORT_TYPE_DEFAULT_COLOR,
)

if TYPE_CHECKING:
    from PySide6.QtGui import QColor

    from core.port import InputPort, OutputPort

    from ui.link_item import LinkItem
    from ui.node_item import NodeItem


PortKind = Literal["input", "output"]


# Qt's drawArc / drawPie work in 1/16-degree units; one full turn is
# 360 * 16. Stored as a constant so the geometry helpers don't sprinkle
# the magic 5760 inline.
_FULL_CIRCLE_16THS: int = 360 * 16


class PortItem(QGraphicsEllipseItem):
    """Small clickable dot at the edge of a node that represents one port.

    Ports are children of their owning :class:`NodeItem` so they move with
    the node. Each port also tracks the :class:`LinkItem` s connected to
    it so link geometry can be refreshed when the node moves.

    Link creation is initiated by pressing the mouse on a port; the scene
    takes over from there (see :class:`FlowScene`).

    Visual encoding (three orthogonal axes):

    * **Type** — ring (and connected-state fill) is a pie of one arc per
      :class:`IoDataType` in the port's accepted/emitted set, coloured
      from :data:`ui.theme.PORT_TYPE_COLORS`. Multi-type ports therefore
      read as multi-coloured rings without any "primary type" heuristic.
    * **Semantics** — ring style differentiates required (thick solid),
      optional input (thin solid) and held input (dashed). Outputs are
      always thick solid.
    * **Direction** — output ports get a small right-pointing triangle
      glyph beside the dot. Input ports stay plain — the position on the
      left edge of the node already disambiguates.
    """

    RADIUS: float = 5.0
    #: Horizontal distance from a port's centre to where its label text
    #: starts. Defined here (rather than as a per-call literal in
    #: :mod:`ui.node_item`) so the relationship between dot radius and
    #: label inset stays in one place — bumping ``RADIUS`` shouldn't
    #: leave the label text overlapping the dot.
    LABEL_OFFSET: float = 11.0  # = RADIUS + 6 px breathing room
    Z_VALUE = 2

    # Ring widths by port semantics. Required inputs and all outputs
    # use the thicker stroke so the type colour stays visible at the
    # default zoom level; optional inputs read as a thinner ring to
    # signal "OK to leave unconnected" without a separate colour axis.
    _RING_WIDTH_DEFAULT: float = 1.4
    _RING_WIDTH_OPTIONAL: float = 1.0

    # Direction glyph (output-only triangle) geometry, in port-local
    # coords. The base sits flush with the right edge of the dot and
    # the tip extends ``_GLYPH_LENGTH`` further out so the arrow reads
    # at typical zoom levels without crowding adjacent ports.
    _GLYPH_BASE_OFFSET: float = 1.0
    _GLYPH_LENGTH: float = 4.5
    _GLYPH_HALF_HEIGHT: float = 3.0

    def __init__(
        self,
        node_item: NodeItem,
        kind: PortKind,
        index: int,
        model: InputPort | OutputPort,
    ) -> None:
        r = self.RADIUS
        super().__init__(-r, -r, 2 * r, 2 * r, parent=node_item)
        self._node_item = node_item
        self._kind: PortKind = kind
        self._index = index
        self._model = model
        self._links: list[LinkItem] = []
        self._hovered: bool = False

        self.setZValue(self.Z_VALUE)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        # All visuals are drawn in :meth:`paint`; suppress the default
        # ellipse pen/brush so Qt doesn't paint a stray outline under
        # our pie-arc ring.
        self.setPen(QPen(Qt.PenStyle.NoPen))
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))

    # ── Identity ───────────────────────────────────────────────────────────────

    @property
    def kind(self) -> PortKind:
        return self._kind

    @property
    def index(self) -> int:
        return self._index

    @property
    def model(self) -> InputPort | OutputPort:
        return self._model

    @property
    def node_item(self) -> NodeItem:
        return self._node_item

    @property
    def name(self) -> str:
        return self._model.name

    # ── Link bookkeeping ───────────────────────────────────────────────────────

    @property
    def links(self) -> list[LinkItem]:
        return list(self._links)

    def add_link(self, link: LinkItem) -> None:
        if link not in self._links:
            self._links.append(link)
            self.update()

    def remove_link(self, link: LinkItem) -> None:
        if link in self._links:
            self._links.remove(link)
            self.update()

    def refresh_links(self) -> None:
        """Called by NodeItem when the node moves so link paths stay glued."""
        for link in self._links:
            link.update_path()

    # ── Hover feedback ─────────────────────────────────────────────────────────

    def hoverEnterEvent(self, event) -> None:  # type: ignore[override]
        self._hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:  # type: ignore[override]
        self._hovered = False
        self.update()
        super().hoverLeaveEvent(event)

    # ── Type / semantics introspection ─────────────────────────────────────────

    def _types(self) -> list[IoDataType]:
        """Return the port's accepted/emitted types in a stable order.

        Sorted by enum-name so a port's ring colours stay put across
        runs and across calls — frozenset iteration order is unspecified.
        """
        if self._kind == "input":
            raw = getattr(self._model, "accepted_types", frozenset())
        else:
            raw = getattr(self._model, "emits", frozenset())
        return sorted(raw, key=lambda t: t.name)

    @staticmethod
    def _type_color(t: IoDataType) -> QColor:
        return PORT_TYPE_COLORS.get(t, PORT_TYPE_DEFAULT_COLOR)

    def _is_connected(self) -> bool:
        """True if this port currently has at least one link.

        Reads from ``self._links`` rather than the underlying model so
        the visual state stays consistent with what the scene drew —
        ``add_link`` / ``remove_link`` are the single source of truth
        for what the user sees.
        """
        return bool(self._links)

    def _is_optional(self) -> bool:
        if self._kind != "input":
            return False
        return bool(getattr(self._model, "optional", False))

    def _is_held(self) -> bool:
        if self._kind != "input":
            return False
        return bool(getattr(self._model, "hold_last", False))

    def _ring_width(self) -> float:
        return self._RING_WIDTH_OPTIONAL if self._is_optional() else self._RING_WIDTH_DEFAULT

    def _ring_style(self) -> Qt.PenStyle:
        return Qt.PenStyle.DashLine if self._is_held() else Qt.PenStyle.SolidLine

    # ── Painting ───────────────────────────────────────────────────────────────

    def paint(self, painter, option, widget=None) -> None:  # type: ignore[override]
        painter.setRenderHint(painter.RenderHint.Antialiasing, True)

        types = self._types()
        rect = self.rect()

        # Interior fill — connection state.
        # Hover wins over everything so the user always gets the same
        # "you're about to grab this dot" feedback.
        if self._hovered:
            painter.setPen(QPen(Qt.PenStyle.NoPen))
            painter.setBrush(QBrush(PORT_HOVER_COLOR))
            painter.drawEllipse(rect)
        elif self._is_connected() and types:
            self._paint_pie(painter, rect, types)
        else:
            painter.setPen(QPen(Qt.PenStyle.NoPen))
            painter.setBrush(QBrush(Qt.GlobalColor.black))
            painter.drawEllipse(rect)

        # Ring — type-coloured arcs on top of the fill.
        self._paint_ring(painter, rect, types)

        # Output direction glyph — drawn last so it sits above any
        # neighbouring ring stroke.
        if self._kind == "output":
            self._paint_direction_glyph(painter)

    def _paint_pie(self, painter, rect: QRectF, types: list[IoDataType]) -> None:
        painter.setPen(QPen(Qt.PenStyle.NoPen))
        if len(types) == 1:
            painter.setBrush(QBrush(self._type_color(types[0])))
            painter.drawEllipse(rect)
            return
        span = _FULL_CIRCLE_16THS // len(types)
        # Distribute any rounding remainder onto the last slice so the
        # pie always closes cleanly with no thin background sliver.
        for i, t in enumerate(types):
            start = i * span
            slice_span = span if i < len(types) - 1 else _FULL_CIRCLE_16THS - start
            painter.setBrush(QBrush(self._type_color(t)))
            painter.drawPie(rect, start, slice_span)

    def _paint_ring(self, painter, rect: QRectF, types: list[IoDataType]) -> None:
        painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        width = self._ring_width()
        style = self._ring_style()
        if not types:
            pen = QPen(PORT_TYPE_DEFAULT_COLOR, width, style)
            painter.setPen(pen)
            painter.drawEllipse(rect)
            return
        if len(types) == 1:
            pen = QPen(self._type_color(types[0]), width, style)
            painter.setPen(pen)
            painter.drawEllipse(rect)
            return
        span = _FULL_CIRCLE_16THS // len(types)
        for i, t in enumerate(types):
            start = i * span
            arc_span = span if i < len(types) - 1 else _FULL_CIRCLE_16THS - start
            pen = QPen(self._type_color(t), width, style)
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            painter.setPen(pen)
            painter.drawArc(rect, start, arc_span)

    def _paint_direction_glyph(self, painter) -> None:
        path = QPainterPath()
        base_x = self.RADIUS + self._GLYPH_BASE_OFFSET
        tip_x = base_x + self._GLYPH_LENGTH
        h = self._GLYPH_HALF_HEIGHT
        path.moveTo(base_x, -h)
        path.lineTo(tip_x, 0.0)
        path.lineTo(base_x, h)
        path.closeSubpath()
        painter.setPen(QPen(Qt.PenStyle.NoPen))
        painter.setBrush(QBrush(PORT_DIRECTION_GLYPH_COLOR))
        painter.drawPath(path)

    # Press handling is intentionally left to the scene: if PortItem grabs
    # the mouse here, Qt routes subsequent move/release events to the item
    # rather than to the scene, which is exactly what the pending-link
    # code path needs to consume. See FlowScene.mousePressEvent.

    def boundingRect(self) -> QRectF:  # type: ignore[override]
        # Slightly larger than the visible ellipse so hit-testing is
        # forgiving. Outputs extend further to the right to cover the
        # direction glyph; without it the arrow would clip when scrolled
        # near the viewport edge.
        r = self.RADIUS + 2
        if self._kind == "output":
            extra = self._GLYPH_BASE_OFFSET + self._GLYPH_LENGTH + 1.0
            return QRectF(-r, -r, 2 * r + extra, 2 * r)
        return QRectF(-r, -r, 2 * r, 2 * r)

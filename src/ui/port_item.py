from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Literal

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QPen
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsItem

from ui.theme import (
    NODE_BORDER_COLOR,
    PORT_HOVER_COLOR,
    PORT_INPUT_COLOR,
    PORT_OUTPUT_COLOR,
)

if TYPE_CHECKING:
    from core.port import InputPort, OutputPort

    from ui.link_item import LinkItem
    from ui.node_item import NodeItem


PortKind = Literal["input", "output"]


class PortItem(QGraphicsEllipseItem):
    """Small clickable dot at the edge of a node that represents one port.

    Ports are children of their owning :class:`NodeItem` so they move with
    the node. Each port also tracks the :class:`LinkItem` s connected to
    it so link geometry can be refreshed when the node moves.

    Link creation is initiated by pressing the mouse on a port; the scene
    takes over from there (see :class:`FlowScene`).
    """

    RADIUS: float = 5.0
    #: Horizontal distance from a port's centre to where its label text
    #: starts. Defined here (rather than as a per-call literal in
    #: :mod:`ui.node_item`) so the relationship between dot radius and
    #: label inset stays in one place — bumping ``RADIUS`` shouldn't
    #: leave the label text overlapping the dot.
    LABEL_OFFSET: float = 11.0  # = RADIUS + 6 px breathing room
    Z_VALUE = 2

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

        self.setZValue(self.Z_VALUE)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        # Pen (outline) by port kind:
        #   * Optional input  → bright PORT_INPUT_COLOR ring (the
        #     pre-existing "OK to leave unconnected" affordance).
        #   * Required input  → subtle dark NODE_BORDER_COLOR.
        #   * Output          → bright PORT_OUTPUT_COLOR ring so the
        #     unconnected fill (set by ``_apply_default_brush``) is
        #     visibly haloed in yellow, mirroring the optional-input
        #     ring on the opposite side of the node.
        # The pen stays put for the lifetime of the port; brush is
        # what tracks connection state via ``_apply_default_brush``.
        if self._kind == "output":
            self.setPen(QPen(PORT_OUTPUT_COLOR, 1.4))
        elif self._is_optional():
            self.setPen(QPen(PORT_INPUT_COLOR, 1.4))
        else:
            self.setPen(QPen(NODE_BORDER_COLOR, 1))
        self._apply_default_brush()

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
            self._apply_default_brush()

    def remove_link(self, link: LinkItem) -> None:
        if link in self._links:
            self._links.remove(link)
            self._apply_default_brush()

    def refresh_links(self) -> None:
        """Called by NodeItem when the node moves so link paths stay glued."""
        for link in self._links:
            link.update_path()

    # ── Hover feedback ─────────────────────────────────────────────────────────

    def hoverEnterEvent(self, event) -> None:  # type: ignore[override]
        self.setBrush(QBrush(PORT_HOVER_COLOR))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:  # type: ignore[override]
        self._apply_default_brush()
        super().hoverLeaveEvent(event)

    def _apply_default_brush(self) -> None:
        # Connection state drives the fill: an unconnected port reads
        # as a "ready to receive" affordance with a black interior; a
        # connected port turns solid in its kind colour to signal the
        # link is live. The pen / outline keeps the port-kind colour
        # in both states so the dot stays identifiable at a glance.
        if self._is_connected():
            color = PORT_OUTPUT_COLOR if self._kind == "output" else PORT_INPUT_COLOR
            self.setBrush(QBrush(color))
        else:
            self.setBrush(QBrush(Qt.black))

    def _is_connected(self) -> bool:
        """True if this port currently has at least one link.

        Reads from ``self._links`` rather than the underlying model so
        the visual state stays consistent with what the scene drew —
        ``add_link`` / ``remove_link`` are the single source of truth
        for what the user sees.
        """
        return bool(self._links)

    def _is_optional(self) -> bool:
        """True if this port is an input marked ``optional=True``.

        Output ports are never optional — only the receiver side can
        choose to run without an incoming payload.
        """
        if self._kind != "input":
            return False
        return bool(getattr(self._model, "optional", False))

    # Press handling is intentionally left to the scene: if PortItem grabs
    # the mouse here, Qt routes subsequent move/release events to the item
    # rather than to the scene, which is exactly what the pending-link
    # code path needs to consume. See FlowScene.mousePressEvent.

    def boundingRect(self) -> QRectF:  # type: ignore[override]
        # Slightly larger than the visible ellipse so hit-testing is forgiving.
        r = self.RADIUS + 2
        return QRectF(-r, -r, 2 * r, 2 * r)

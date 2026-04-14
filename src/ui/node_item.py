from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsProxyWidget,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from core.node_base import NodeBase, SinkNodeBase, SourceNodeBase
from ui.param_widgets import build_param_widget
from ui.port_item import PortItem
from ui.theme import (
    FILTER_HEADER_COLOR,
    NODE_BODY_COLOR,
    NODE_BORDER_COLOR,
    NODE_BORDER_SELECTED,
    NODE_PARAM_LABEL_COLOR,
    NODE_TITLE_TEXT_COLOR,
    SINK_HEADER_COLOR,
    SOURCE_HEADER_COLOR,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class NodeItem(QGraphicsItem):
    """A single node drawn on the flow canvas.

    Visual layout (top to bottom):

        ┌──────────────────────────┐
        │  header (category color) │   node.display_name
        ├──────────────────────────┤
        │  param rows (QWidget)    │   one label + editor per NodeParam
        ├──────────────────────────┤
        │◉ in_name    out_name   ◉│   port rows; inputs left, outputs right
        │◉ in_name    out_name   ◉│
        └──────────────────────────┘

    Parameter widgets are embedded via a :class:`QGraphicsProxyWidget`
    so the native Qt form controls (line edit, spin box, browse button)
    behave exactly as they would in any dialog.
    """

    WIDTH: float = 220.0
    HEADER_HEIGHT: float = 28.0
    PORT_ROW_HEIGHT: float = 22.0
    CORNER_RADIUS: float = 5.0
    PADDING: float = 8.0
    PARAM_GAP: float = 4.0

    Z_VALUE = 1

    def __init__(self, node: NodeBase) -> None:
        super().__init__()
        self._node = node
        self._input_ports: list[PortItem] = []
        self._output_ports: list[PortItem] = []
        self._params_widget: QWidget | None = None
        self._proxy: QGraphicsProxyWidget | None = None
        self._params_height: float = 0.0
        self._body_height: float = 0.0

        self.setZValue(self.Z_VALUE)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsScenePositionChanges, True)

        self._build_params_widget()
        self._build_ports()
        self._do_layout()

    # ── Public API ─────────────────────────────────────────────────────────────

    @property
    def node(self) -> NodeBase:
        return self._node

    @property
    def input_ports(self) -> list[PortItem]:
        return list(self._input_ports)

    @property
    def output_ports(self) -> list[PortItem]:
        return list(self._output_ports)

    def input_port(self, index: int) -> PortItem:
        return self._input_ports[index]

    def output_port(self, index: int) -> PortItem:
        return self._output_ports[index]

    def refresh_all_links(self) -> None:
        """Re-route every link attached to every port of this node."""
        for p in self._input_ports:
            p.refresh_links()
        for p in self._output_ports:
            p.refresh_links()

    # ── Graphics item overrides ────────────────────────────────────────────────

    def boundingRect(self) -> QRectF:  # type: ignore[override]
        return QRectF(-2, -2, self.WIDTH + 4, self._body_height + 4)

    def paint(self, painter: QPainter, option, widget=None) -> None:  # type: ignore[override]
        painter.setRenderHint(QPainter.Antialiasing, True)

        body_rect = QRectF(0, 0, self.WIDTH, self._body_height)
        border_pen = QPen(
            NODE_BORDER_SELECTED if self.isSelected() else NODE_BORDER_COLOR,
            2 if self.isSelected() else 1,
        )

        # ── body ──
        painter.setPen(border_pen)
        painter.setBrush(QBrush(NODE_BODY_COLOR))
        painter.drawRoundedRect(body_rect, self.CORNER_RADIUS, self.CORNER_RADIUS)

        # ── header (rounded top corners only) ──
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(self._header_color()))
        painter.drawPath(self._header_path())

        # ── title text ──
        painter.setPen(QPen(NODE_TITLE_TEXT_COLOR))
        painter.drawText(
            QRectF(self.PADDING, 0, self.WIDTH - 2 * self.PADDING, self.HEADER_HEIGHT),
            Qt.AlignVCenter | Qt.AlignLeft,
            self._node.display_name,
        )

        # ── port labels ──
        painter.setPen(QPen(NODE_PARAM_LABEL_COLOR))
        io_top = self._io_top()
        label_margin = PortItem.RADIUS + 6

        for i, port in enumerate(self._input_ports):
            y = io_top + (i + 0.5) * self.PORT_ROW_HEIGHT
            painter.drawText(
                QRectF(label_margin, y - self.PORT_ROW_HEIGHT / 2,
                       self.WIDTH - 2 * label_margin, self.PORT_ROW_HEIGHT),
                Qt.AlignVCenter | Qt.AlignLeft,
                port.name,
            )
        for i, port in enumerate(self._output_ports):
            y = io_top + (i + 0.5) * self.PORT_ROW_HEIGHT
            painter.drawText(
                QRectF(label_margin, y - self.PORT_ROW_HEIGHT / 2,
                       self.WIDTH - 2 * label_margin, self.PORT_ROW_HEIGHT),
                Qt.AlignVCenter | Qt.AlignRight,
                port.name,
            )

    def itemChange(self, change, value):  # type: ignore[override]
        # When the node moves, reroute every attached link so they stay
        # glued to the port dots.
        if change == QGraphicsItem.ItemScenePositionHasChanged:
            self.refresh_all_links()
        return super().itemChange(change, value)

    # ── Internals ──────────────────────────────────────────────────────────────

    def _header_color(self):
        if isinstance(self._node, SourceNodeBase):
            return SOURCE_HEADER_COLOR
        if isinstance(self._node, SinkNodeBase):
            return SINK_HEADER_COLOR
        return FILTER_HEADER_COLOR

    def _header_path(self) -> QPainterPath:
        """Path for the header: top corners rounded, bottom corners square."""
        w = self.WIDTH
        h = self.HEADER_HEIGHT
        r = self.CORNER_RADIUS
        path = QPainterPath()
        path.moveTo(0, h)
        path.lineTo(0, r)
        path.quadTo(0, 0, r, 0)
        path.lineTo(w - r, 0)
        path.quadTo(w, 0, w, r)
        path.lineTo(w, h)
        path.closeSubpath()
        return path

    def _io_top(self) -> float:
        return self.HEADER_HEIGHT + self._params_height + (self.PARAM_GAP if self._params_height else 0)

    def _build_params_widget(self) -> None:
        if not self._node.params:
            return
        w = QWidget()
        w.setAttribute(Qt.WA_TranslucentBackground, True)
        w.setStyleSheet("QWidget { background: transparent; }")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(int(self.PADDING), int(self.PADDING), int(self.PADDING), 0)
        layout.setSpacing(2)

        for param in self._node.params:
            name_label = QLabel(param.name)
            name_label.setProperty("muted", True)
            layout.addWidget(name_label)
            editor = build_param_widget(self._node, param)
            if editor is not None:
                layout.addWidget(editor)
            else:
                layout.addWidget(QLabel(f"(unsupported: {param.param_type.name})"))

        self._params_widget = w
        self._proxy = QGraphicsProxyWidget(self)
        self._proxy.setWidget(w)

    def _build_ports(self) -> None:
        self._input_ports = [
            PortItem(self, "input", i, port) for i, port in enumerate(self._node.inputs)
        ]
        self._output_ports = [
            PortItem(self, "output", i, port) for i, port in enumerate(self._node.outputs)
        ]

    def _do_layout(self) -> None:
        # Parameter widget sized to the node width.
        if self._params_widget is not None and self._proxy is not None:
            self._params_widget.setFixedWidth(int(self.WIDTH - 2))
            self._params_height = float(self._params_widget.sizeHint().height())
            self._proxy.setPos(1.0, self.HEADER_HEIGHT)

        # Ports stacked below the params section.
        io_top = self._io_top()
        for i, port in enumerate(self._input_ports):
            port.setPos(0.0, io_top + (i + 0.5) * self.PORT_ROW_HEIGHT)
        for i, port in enumerate(self._output_ports):
            port.setPos(self.WIDTH, io_top + (i + 0.5) * self.PORT_ROW_HEIGHT)

        n_rows = max(len(self._input_ports), len(self._output_ports), 0)
        io_height = n_rows * self.PORT_ROW_HEIGHT
        self._body_height = io_top + io_height + self.PADDING

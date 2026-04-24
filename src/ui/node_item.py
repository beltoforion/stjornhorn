from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetricsF,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsItem,
    QGraphicsProxyWidget,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from core.node_base import NodeBase, SinkNodeBase, SourceNodeBase
from ui.param_widgets import ParamWidgetBase, build_param_widget
from ui.port_item import PortItem
from ui.preview_widgets import build_preview_widget
from ui.theme import (
    FILTER_HEADER_COLOR,
    NODE_BODY_COLOR,
    NODE_BORDER_COLOR,
    NODE_BORDER_SELECTED,
    NODE_PARAM_LABEL_COLOR,
    NODE_SKIPPED_HEADER_COLOR,
    NODE_TITLE_TEXT_COLOR,
    SINK_HEADER_COLOR,
    SOURCE_HEADER_COLOR,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class _NodeSignals(QObject):
    """QObject signal carrier for :class:`NodeItem`.

    ``NodeItem`` inherits from ``QGraphicsItem`` (not ``QGraphicsObject``)
    to avoid a shiboken multiple-inheritance pointer-aliasing issue where
    ``QGraphicsScene.selectedItems()`` cannot resolve the Python wrapper of a
    ``QGraphicsObject`` subclass and returns a bare ``QGraphicsObject``
    instead, breaking ``isinstance`` checks.  This helper carries the signals
    that ``NodeItem`` needs.
    """

    #: Emitted when any parameter widget on the owning node changes value.
    param_changed = Signal()


class _ResizeGripItem(QGraphicsItem):
    """Bottom-right drag handle that resizes the owning node.

    Width is always user-adjustable; dragging past :data:`NodeItem.MIN_WIDTH`
    or :data:`NodeItem.MAX_USER_WIDTH` clamps. Vertical drag only changes
    the node's height when the node has a preview widget (otherwise
    content dictates height).
    """

    SIZE: float = 12.0
    Z_VALUE = 2

    def __init__(self, node_item: "NodeItem") -> None:
        super().__init__(parent=node_item)
        self._node_item = node_item
        self._drag_origin: QPointF | None = None
        self._drag_start_w: float = 0.0
        self._drag_start_h: float = 0.0
        self.setZValue(self.Z_VALUE)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setCursor(Qt.CursorShape.SizeFDiagCursor)

    def boundingRect(self) -> QRectF:  # type: ignore[override]
        return QRectF(0, 0, self.SIZE, self.SIZE)

    def paint(self, painter: QPainter, option, widget=None) -> None:  # type: ignore[override]
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(QColor(180, 180, 180, 180), 1.2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        s = self.SIZE
        # Three diagonal grip lines, widely-recognised resize affordance.
        for offset in (0.2, 0.5, 0.8):
            painter.drawLine(
                QPointF(s, s * offset),
                QPointF(s * offset, s),
            )

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        self._drag_origin = event.scenePos()
        self._drag_start_w = self._node_item.width
        self._drag_start_h = self._node_item.body_height
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._drag_origin is None:
            super().mouseMoveEvent(event)
            return
        delta = event.scenePos() - self._drag_origin
        self._node_item.apply_user_size(
            self._drag_start_w + delta.x(),
            self._drag_start_h + delta.y(),
        )
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton and self._drag_origin is not None:
            self._drag_origin = None
            event.accept()
            return
        super().mouseReleaseEvent(event)


class _CloseButtonItem(QGraphicsItem):
    """Small ``X`` button rendered on the right of a node header.

    Clicking it asks the owning scene to delete the node. Kept as a child
    ``QGraphicsItem`` of the node so it moves and z-orders with the header.
    """

    SIZE: float = 14.0
    Z_VALUE = 2

    def __init__(self, node_item: "NodeItem") -> None:
        super().__init__(parent=node_item)
        self._node_item = node_item
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
                node_item = self._node_item
                if scene is not None and hasattr(scene, "remove_node_item"):
                    # Defer so we don't delete ourselves while still inside
                    # our own event handler.
                    QTimer.singleShot(0, lambda: scene.remove_node_item(node_item))
            event.accept()
            return
        super().mouseReleaseEvent(event)


class _SkipButtonItem(QGraphicsItem):
    """Toggle button rendered on the left of the close button in a node header.

    Only attached to nodes whose :attr:`NodeBase.is_skippable` is True.
    Clicking it toggles :attr:`NodeBase.skipped`; while skipped, the
    owning node forwards each input to the matching output in place of
    its normal ``process_impl``, the header is painted grey and the
    title is struck through.

    Draws a simple double-chevron (``»``) glyph so the affordance reads
    as "pass through / skip forward" without needing a separate icon
    font.
    """

    SIZE: float = 14.0
    Z_VALUE = 2

    def __init__(self, node_item: "NodeItem") -> None:
        super().__init__(parent=node_item)
        self._node_item = node_item
        self._hovered = False
        self._pressed = False
        self.setZValue(self.Z_VALUE)
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setToolTip("Skip this node (pass inputs straight through)")

    def boundingRect(self) -> QRectF:  # type: ignore[override]
        return QRectF(0, 0, self.SIZE, self.SIZE)

    def paint(self, painter: QPainter, option, widget=None) -> None:  # type: ignore[override]
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        active = self._node_item.node.skipped
        if self._hovered or self._pressed or active:
            painter.setPen(Qt.NoPen)
            alpha = 120 if active else 70
            painter.setBrush(QBrush(QColor(255, 255, 255, alpha)))
            painter.drawRoundedRect(self.boundingRect(), 2, 2)

        pen = QPen(NODE_TITLE_TEXT_COLOR, 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        s = self.SIZE
        # Two right-pointing chevrons, rendered as thin V shapes, echoing
        # the ``»`` symbol.
        mid_y = s / 2
        tip_dx = 3.0
        half_h = 3.0
        for x_tip in (s * 0.58, s * 0.86):
            painter.drawLine(
                QPointF(x_tip - tip_dx, mid_y - half_h),
                QPointF(x_tip, mid_y),
            )
            painter.drawLine(
                QPointF(x_tip, mid_y),
                QPointF(x_tip - tip_dx, mid_y + half_h),
            )

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
                self._node_item.toggle_skipped()
            self.update()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class NodeItem(QGraphicsItem):
    """A single node drawn on the flow canvas.

    Visual layout (top to bottom):

        ┌──────────────────────────┐
        │  header (category color) │   node.display_name
        ├──────────────────────────┤
        │  param rows (QWidget)    │   one label + editor per NodeParam
        ├──────────────────────────┤
        │◉ in_name    out_name    ◉│   port rows; inputs left, outputs right
        │◉ in_name    out_name    ◉│
        └──────────────────────────┘

    Parameter widgets are embedded via a :class:`QGraphicsProxyWidget`
    so the native Qt form controls (line edit, spin box, browse button)
    behave exactly as they would in any dialog.
    """

    MIN_WIDTH: float = 120.0
    MAX_WIDTH: float = 220.0      # natural (content-driven) upper bound
    MAX_USER_WIDTH: float = 800.0 # cap when the user drags the resize grip
    MAX_USER_HEIGHT: float = 1000.0
    HEADER_HEIGHT: float = 28.0
    PORT_ROW_HEIGHT: float = 22.0
    CORNER_RADIUS: float = 5.0
    PADDING: float = 8.0
    PARAM_GAP: float = 4.0
    CLOSE_BUTTON_SIZE: float = 14.0
    SKIP_BUTTON_SIZE: float = 14.0
    HEADER_BUTTON_GAP: float = 4.0
    RESIZE_GRIP_SIZE: float = 12.0
    PORT_LABEL_GAP: float = 12.0  # min gap between paired input/output labels

    Z_VALUE = 1

    def __init__(self, node: NodeBase) -> None:
        super().__init__()
        self._node = node
        self._signals = _NodeSignals()
        self._input_ports: list[PortItem] = []
        self._output_ports: list[PortItem] = []
        self._params_widget: QWidget | None = None  # container; holds ParamWidgetBases
        self._param_widgets: list[ParamWidgetBase] = []
        self._preview_widget: QWidget | None = None
        self._proxy: QGraphicsProxyWidget | None = None
        self._params_height: float = 0.0
        self._body_height: float = 0.0
        self._width: float = self.MAX_WIDTH
        # User-chosen overrides (from resize grip or flow load). None
        # means "use the natural, content-driven size".
        self._user_width: float | None = None
        self._user_height: float | None = None

        self.setZValue(self.Z_VALUE)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsScenePositionChanges, True)

        self._close_button = _CloseButtonItem(self)
        self._skip_button: _SkipButtonItem | None = (
            _SkipButtonItem(self) if node.is_skippable else None
        )
        self._resize_grip = _ResizeGripItem(self)

        self._build_params_widget()
        self._build_ports()
        self._relayout()

    # ── Public API ─────────────────────────────────────────────────────────────

    @property
    def node(self) -> NodeBase:
        return self._node

    @property
    def signals(self) -> _NodeSignals:
        """Signal carrier; use ``node_item.signals.param_changed`` to connect."""
        return self._signals

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

    @property
    def width(self) -> float:
        """The node's current body width."""
        return self._width

    @property
    def body_height(self) -> float:
        """The node's current body height."""
        return self._body_height

    @property
    def user_size(self) -> tuple[float | None, float | None]:
        """User-chosen (width, height) overrides, or ``(None, None)`` if
        the node is at its natural content-driven size. Flow I/O reads
        this to persist resizes across sessions."""
        return (self._user_width, self._user_height)

    def apply_user_size(self, width: float, height: float) -> None:
        """Set an explicit body size (clamped) and relayout.

        Called by :class:`_ResizeGripItem` during drag and by
        :meth:`core.flow_io.flow_from_dict` when restoring a saved flow.
        Either coordinate may be passed as a hint; the layout pass
        clamps them to legal ranges.
        """
        self._user_width = float(width)
        self._user_height = float(height)
        self._relayout()

    def clear_user_size(self) -> None:
        """Revert to content-driven natural sizing."""
        self._user_width = None
        self._user_height = None
        self._relayout()

    def boundingRect(self) -> QRectF:  # type: ignore[override]
        return QRectF(-2, -2, self._width + 4, self._body_height + 4)

    def paint(self, painter: QPainter, option, widget=None) -> None:  # type: ignore[override]
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        body_rect = QRectF(0, 0, self._width, self._body_height)
        border_pen = QPen(
            NODE_BORDER_SELECTED if self.isSelected() else NODE_BORDER_COLOR,
            2 if self.isSelected() else 1,
        )

        # Draw fill, header, and border in three passes so that the
        # selection border is always rendered LAST — otherwise the header
        # path (which covers the full node width) overpaints the inside
        # half of the border along the top edges and the yellow selection
        # marker appears chewed at the top-left / top-right.

        # ── body fill ──
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(NODE_BODY_COLOR))
        painter.drawRoundedRect(body_rect, self.CORNER_RADIUS, self.CORNER_RADIUS)

        # ── header (rounded top corners only) ──
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(self._header_color()))
        painter.drawPath(self._header_path())

        # ── border (stroked on top so nothing covers it) ──
        painter.setPen(border_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(body_rect, self.CORNER_RADIUS, self.CORNER_RADIUS)

        # ── title text ──
        painter.setPen(QPen(NODE_TITLE_TEXT_COLOR))
        title_right_reserve = self._title_right_reserve()
        if self._node.skipped:
            title_font = QFont(painter.font())
            title_font.setStrikeOut(True)
            painter.setFont(title_font)
        painter.drawText(
            QRectF(
                self.PADDING,
                0,
                self._width - 2 * self.PADDING - title_right_reserve,
                self.HEADER_HEIGHT,
            ),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
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
                       self._width - 2 * label_margin, self.PORT_ROW_HEIGHT),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                port.name,
            )
        for i, port in enumerate(self._output_ports):
            y = io_top + (i + 0.5) * self.PORT_ROW_HEIGHT
            painter.drawText(
                QRectF(label_margin, y - self.PORT_ROW_HEIGHT / 2,
                       self._width - 2 * label_margin, self.PORT_ROW_HEIGHT),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                port.name,
            )

    def itemChange(self, change, value):  # type: ignore[override]
        # When the node moves, reroute every attached link so they stay
        # glued to the port dots.
        if change == QGraphicsItem.GraphicsItemChange.ItemScenePositionHasChanged:
            self.refresh_all_links()
            
        return super().itemChange(change, value)

    # ── Internals ──────────────────────────────────────────────────────────────

    def _header_color(self):
        if self._node.skipped:
            return NODE_SKIPPED_HEADER_COLOR
        if isinstance(self._node, SourceNodeBase):
            return SOURCE_HEADER_COLOR
        if isinstance(self._node, SinkNodeBase):
            return SINK_HEADER_COLOR

        return FILTER_HEADER_COLOR

    def _title_right_reserve(self) -> float:
        """Horizontal space reserved in the header for right-aligned buttons."""
        reserve = self.CLOSE_BUTTON_SIZE + self.PADDING
        if self._skip_button is not None:
            reserve += self.SKIP_BUTTON_SIZE + self.HEADER_BUTTON_GAP
        return reserve

    def toggle_skipped(self) -> None:
        """Flip the node's skipped state and refresh the visual."""
        self._node.skipped = not self._node.skipped
        if self._skip_button is not None:
            self._skip_button.update()
        self.update()

    def _header_path(self) -> QPainterPath:
        """Path for the header: top corners rounded, bottom corners square."""
        w = self._width
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

    def _compute_width(self) -> float:
        """Pick a body width that fits the node's content, clamped to MAX_WIDTH.

        Considers the header title (plus close button), each paired
        input/output port label row, and the params widget's sizeHint.
        The MAX_WIDTH clamp matches the legacy fixed layout width so
        long labels never blow past the expected canvas budget.
        """
        padding = self.PADDING
        metrics = QFontMetricsF(QApplication.font())

        title_w = metrics.horizontalAdvance(self._node.display_name)
        header_need = 2 * padding + title_w + self._title_right_reserve()

        port_margin = PortItem.RADIUS + 6.0
        port_need = 0.0
        rows = max(len(self._input_ports), len(self._output_ports))
        for i in range(rows):
            in_w = (metrics.horizontalAdvance(self._input_ports[i].name)
                    if i < len(self._input_ports) else 0.0)
            out_w = (metrics.horizontalAdvance(self._output_ports[i].name)
                     if i < len(self._output_ports) else 0.0)
            row_need = 2 * port_margin + in_w + self.PORT_LABEL_GAP + out_w
            port_need = max(port_need, row_need)

        params_need = 0.0
        if self._params_widget is not None:
            # +2 mirrors the 1px left/right inset applied in _relayout.
            params_need = float(self._params_widget.sizeHint().width()) + 2.0

        content = max(header_need, port_need, params_need)
        return max(self.MIN_WIDTH, min(self.MAX_WIDTH, content))

    def refresh_param_widgets(self) -> None:
        """Ask every param widget to re-evaluate external state.

        Used by the editor after a flow run so that e.g. FileSink's
        ``view`` button can recognise output files that have just
        appeared on disk.
        """
        for editor in self._param_widgets:
            editor.refresh()

    def set_params_enabled(self, enabled: bool) -> None:
        """Enable or disable every param editor on this node.

        Used by the editor to freeze inputs while the flow is running on a
        worker thread: a setter firing mid-``process_impl`` would race with
        the node reading its own state. Disabling the widgets sidesteps that
        cleanly — the user simply cannot edit until the run completes.
        """
        for editor in self._param_widgets:
            editor.setEnabled(enabled)

    def _build_params_widget(self) -> None:
        preview = build_preview_widget(self._node)
        if not self._node.params and preview is None:
            return
        w = QWidget()
        w.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        w.setStyleSheet("QWidget { background: transparent; }")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(int(self.PADDING), int(self.PADDING), int(self.PADDING), 0)
        layout.setSpacing(2)

        for param in self._node.params:
            name_label = QLabel(param.name)
            name_label.setProperty("muted", True)
            layout.addWidget(name_label)
            editor: ParamWidgetBase | None = build_param_widget(self._node, param)
            if editor is not None:
                editor.value_changed.connect(lambda _v: self._signals.param_changed.emit())
                layout.addWidget(editor)
                self._param_widgets.append(editor)
            else:
                layout.addWidget(QLabel(f"(unsupported: {param.param_type.name})"))

        if preview is not None:
            # Stretch factor 1 — when the user drags the resize grip the
            # params widget is given a fixed height, and the QVBoxLayout
            # funnels the spare vertical space into the preview.
            layout.addWidget(preview, 1)
            self._preview_widget = preview

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

    def _relayout(self) -> None:
        """Recompute width / body height and place every child item.

        Honours user-chosen overrides (via :meth:`apply_user_size`) and
        otherwise falls back to content-driven natural dimensions.
        Callable repeatedly — called on construction and every resize.
        """
        self.prepareGeometryChange()

        # ── Width ──────────────────────────────────────────────────────────────
        if self._user_width is not None:
            self._width = max(self.MIN_WIDTH, min(self.MAX_USER_WIDTH, self._user_width))
        else:
            self._width = self._compute_width()

        # ── Natural params height (used as a floor for user-set heights) ──────
        natural_params_h = 0.0
        if self._params_widget is not None and self._proxy is not None:
            self._params_widget.setFixedWidth(int(self._width - 2))
            # Temporarily clear any fixed height so sizeHint reflects content.
            self._params_widget.setMinimumHeight(0)
            self._params_widget.setMaximumHeight(16777215)
            natural_params_h = float(self._params_widget.sizeHint().height())

        n_rows = max(len(self._input_ports), len(self._output_ports), 0)
        io_height = n_rows * self.PORT_ROW_HEIGHT
        natural_body_h = (
            self.HEADER_HEIGHT
            + natural_params_h
            + (self.PARAM_GAP if natural_params_h else 0)
            + io_height
            + self.PADDING
        )

        # ── Body height ────────────────────────────────────────────────────────
        if self._user_height is not None and self._preview_widget is not None:
            # Only nodes that have something that can stretch (a preview)
            # honour vertical resize. For others the grip's Y drag is
            # absorbed without effect.
            self._body_height = max(
                natural_body_h,
                min(self.MAX_USER_HEIGHT, self._user_height),
            )
        else:
            self._body_height = natural_body_h

        # Distribute body height to params widget so the preview
        # (with stretch=1) gets the leftover space.
        if self._params_widget is not None and self._proxy is not None:
            params_h = self._body_height - self.HEADER_HEIGHT - io_height - self.PADDING
            params_h = max(natural_params_h, params_h)
            self._params_widget.setFixedHeight(int(params_h))
            self._params_height = params_h
            self._proxy.setPos(1.0, self.HEADER_HEIGHT)

        # ── Reposition handles & ports ─────────────────────────────────────────
        self._close_button.setPos(
            self._width - self.PADDING - self.CLOSE_BUTTON_SIZE,
            (self.HEADER_HEIGHT - self.CLOSE_BUTTON_SIZE) / 2,
        )
        if self._skip_button is not None:
            self._skip_button.setPos(
                self._width - self.PADDING - self.CLOSE_BUTTON_SIZE
                - self.HEADER_BUTTON_GAP - self.SKIP_BUTTON_SIZE,
                (self.HEADER_HEIGHT - self.SKIP_BUTTON_SIZE) / 2,
            )
        self._resize_grip.setPos(
            self._width - self.RESIZE_GRIP_SIZE - 1,
            self._body_height - self.RESIZE_GRIP_SIZE - 1,
        )

        io_top = self._io_top()
        for i, port in enumerate(self._input_ports):
            port.setPos(0.0, io_top + (i + 0.5) * self.PORT_ROW_HEIGHT)
        for i, port in enumerate(self._output_ports):
            port.setPos(self._width, io_top + (i + 0.5) * self.PORT_ROW_HEIGHT)

        self.refresh_all_links()
        self.update()

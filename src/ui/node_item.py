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
        │◉ image                  ◉│   image-flow port row (no widget)
        │◉ angle      [ slider  ]  │   param-style port row: socket dot +
        │◉ scale      [ spinbox ]  │   name + inline editor (Blender-style)
        │  preview pixmap / text   │   optional preview, fills spare height
        └──────────────────────────┘

    Each editable input port hosts its own inline widget on the same
    row as its socket dot; the widget is built by
    :func:`ui.param_widgets.build_param_widget` from the port's
    metadata and embedded via a :class:`QGraphicsProxyWidget`.
    Image-flow inputs have no widget — just the socket dot + name.
    """

    # ── Body sizing ────────────────────────────────────────────────────────────
    MIN_WIDTH: float = 120.0
    #: Natural (content-driven) upper bound on the auto-fit width.
    #: Sized to fit a multi-element inline widget (FilePathParamWidget's
    #: line-edit + Browse + View ≈ 160 px) next to a port label
    #: without overlapping.
    MAX_WIDTH: float = 320.0
    #: Cap when the user drags the resize grip wider.
    MAX_USER_WIDTH: float = 800.0
    MAX_USER_HEIGHT: float = 1000.0

    # ── Vertical metrics ───────────────────────────────────────────────────────
    HEADER_HEIGHT: float = 28.0
    #: Tall enough that a native QSpinBox / QLineEdit renders its
    #: full-size up/down arrows and text caret. Smaller and the OS
    #: style squeezes the spinner button icons into a few pixels.
    PORT_ROW_HEIGHT: float = 28.0
    PADDING: float = 8.0
    PARAM_GAP: float = 4.0

    # ── Header chrome ──────────────────────────────────────────────────────────
    CORNER_RADIUS: float = 5.0
    CLOSE_BUTTON_SIZE: float = 14.0
    SKIP_BUTTON_SIZE: float = 14.0
    HEADER_BUTTON_GAP: float = 4.0
    RESIZE_GRIP_SIZE: float = 12.0

    # ── Port row geometry ──────────────────────────────────────────────────────
    #: Horizontal inset between a row's port label and the inline param
    #: widget (or the right edge if no widget). Kept symmetric on both
    #: sides of the widget so the gap reads visually balanced.
    WIDGET_INSET: float = 4.0
    #: Minimum gap reserved between a port label and the right edge
    #: when no widget is present (legacy plain-port row budget).
    PORT_LABEL_GAP: float = 12.0

    Z_VALUE = 1

    def __init__(self, node: NodeBase) -> None:
        super().__init__()
        self._node = node
        self._signals = _NodeSignals()
        self._input_ports: list[PortItem] = []
        self._output_ports: list[PortItem] = []
        # Each param-style input port gets its own inline editor proxy
        # built in _build_ports; the dicts there map port-index → widget
        # so _relayout can position one per row. Preview (Display's
        # pixmap) lives in its own proxy below the IO rows.
        self._param_widgets: list[ParamWidgetBase] = []
        self._param_widgets_by_row: dict[int, ParamWidgetBase] = {}
        self._param_proxies_by_row: dict[int, QGraphicsProxyWidget] = {}
        self._preview_widget: QWidget | None = None
        self._preview_proxy: QGraphicsProxyWidget | None = None
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
        title_left = self._title_left()
        title_right_reserve = self._title_right_reserve()
        if self._node.skipped:
            title_font = QFont(painter.font())
            title_font.setStrikeOut(True)
            painter.setFont(title_font)
        painter.drawText(
            QRectF(
                title_left,
                0,
                self._width - title_left - self.PADDING - title_right_reserve,
                self.HEADER_HEIGHT,
            ),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self._node.display_name,
        )

        # ── port labels ──
        painter.setPen(QPen(NODE_PARAM_LABEL_COLOR))
        label_inset = PortItem.LABEL_OFFSET

        # Outputs sit at the top of the body (right-aligned).
        outputs_top = self._outputs_top()
        for i, port in enumerate(self._output_ports):
            y = outputs_top + (i + 0.5) * self.PORT_ROW_HEIGHT
            painter.drawText(
                QRectF(label_inset, y - self.PORT_ROW_HEIGHT / 2,
                       self._width - 2 * label_inset, self.PORT_ROW_HEIGHT),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                port.name,
            )
        # Inputs follow below; rows with a widget truncate the label.
        inputs_top = self._inputs_top()
        for i, port in enumerate(self._input_ports):
            y = inputs_top + (i + 0.5) * self.PORT_ROW_HEIGHT
            label_right = self._width - label_inset
            proxy = self._param_proxies_by_row.get(i)
            if proxy is not None:
                label_right = proxy.pos().x() - self.WIDGET_INSET
            painter.drawText(
                QRectF(label_inset, y - self.PORT_ROW_HEIGHT / 2,
                       max(0.0, label_right - label_inset),
                       self.PORT_ROW_HEIGHT),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
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
        """Horizontal space reserved on the header's right edge for buttons."""
        return self.CLOSE_BUTTON_SIZE + self.PADDING

    def _title_left(self) -> float:
        """X offset where the title text starts, accounting for the left-side
        skip button when the node is skippable."""
        if self._skip_button is not None:
            return self.PADDING + self.SKIP_BUTTON_SIZE + self.HEADER_BUTTON_GAP
        return self.PADDING

    def toggle_skipped(self) -> None:
        """Flip the node's skipped state and refresh the visual."""
        self._node.skipped = not self._node.skipped
        if self._skip_button is not None:
            self._skip_button.update()
        self.update()
        # Skip-state flips behave like param edits from the user's
        # perspective (they change what the flow does on the next run),
        # so piggy-back on param_changed to drive auto-run + dirty.
        self._signals.param_changed.emit()

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

    def _outputs_top(self) -> float:
        """Y of the first output row — output sockets are stacked at
        the top of the body, right under the header (Blender-style)."""
        return self.HEADER_HEIGHT

    def _inputs_top(self) -> float:
        """Y of the first input row — inputs sit below the output
        block. Param-style inputs carry an inline widget on the same
        row as their socket dot."""
        return self.HEADER_HEIGHT + len(self._output_ports) * self.PORT_ROW_HEIGHT

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
        left_reserve = self._title_left()
        header_need = left_reserve + title_w + padding + self._title_right_reserve()

        label_inset = PortItem.LABEL_OFFSET
        port_need = 0.0

        # Outputs are stacked at the top of the body — each row only
        # needs room for the right-edge socket dot + label.
        for port in self._output_ports:
            row_need = 2 * label_inset + metrics.horizontalAdvance(port.name)
            port_need = max(port_need, row_need)

        # Plain image-flow inputs (no widget) just need room for the
        # left-edge socket dot + label.
        for i, port in enumerate(self._input_ports):
            if i in self._param_widgets_by_row:
                continue
            row_need = 2 * label_inset + metrics.horizontalAdvance(port.name)
            port_need = max(port_need, row_need)

        # Inputs with widgets line up along a single shared widget-X
        # anchor (see :meth:`_layout_param_widgets`) so the widget
        # column reads as a clean vertical stack regardless of how
        # short or long each label is. The anchor sits past the
        # *longest* label, so the natural-width budget grows to fit
        # ``label_inset + max_label_w + WIDGET_INSET + max_widget_min
        # + WIDGET_INSET`` — once at the longest label, once at the
        # widest widget-min in the same node.
        if self._param_widgets_by_row:
            max_label_w = max(
                metrics.horizontalAdvance(self._input_ports[i].name)
                for i in self._param_widgets_by_row
            )
            max_widget_min_w = max(
                float(editor.minimumSizeHint().width())
                for editor in self._param_widgets_by_row.values()
            )
            row_need = (
                label_inset + max_label_w
                + 2 * self.WIDGET_INSET
                + max_widget_min_w
            )
            port_need = max(port_need, row_need)

        # Preview widget asks for as much width as it can get; cap at
        # MAX_WIDTH via the outer min() below.
        preview_need = 0.0
        if self._preview_widget is not None:
            preview_need = float(self._preview_widget.sizeHint().width()) + 2 * self.PADDING

        content = max(header_need, port_need, preview_need)
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

    def _build_ports(self) -> None:
        """Build PortItems and the per-row inline widgets (param sockets).

        Each input port becomes a :class:`PortItem`; if its underlying
        :class:`InputPort` is param-style (metadata carries
        ``"param_type"``), an inline editor widget is attached to the
        same row via a :class:`QGraphicsProxyWidget`. The widget is
        positioned in :meth:`_relayout` to sit on the same horizontal
        row as the port dot. The widget is disabled at construction
        when ``port.upstream is not None`` — a streamed value would
        override whatever the slider writes, so leaving the editor
        live would be misleading. Live refresh on connect/disconnect
        is intentionally not wired (would race with link drag/drop in
        practice); the user re-opens / reloads the flow to pick up
        changes.
        """
        self._input_ports = []
        # Per input-port-index → editor (if param-style) and proxy.
        # Using parallel dicts keyed by port index so a layout pass
        # can find the right widget for row N without walking lists.
        self._param_widgets_by_row: dict[int, ParamWidgetBase] = {}
        self._param_proxies_by_row: dict[int, QGraphicsProxyWidget] = {}

        for i, port_model in enumerate(self._node.inputs):
            port_item = PortItem(self, "input", i, port_model)
            self._input_ports.append(port_item)
            if "param_type" not in port_model.metadata:
                continue
            editor = build_param_widget(self._node, port_model)
            if editor is None:
                continue
            editor.value_changed.connect(
                lambda _v: self._signals.param_changed.emit()
            )
            editor.setEnabled(port_model.upstream is None)
            proxy = QGraphicsProxyWidget(self)
            proxy.setWidget(editor)
            self._param_widgets_by_row[i] = editor
            self._param_proxies_by_row[i] = proxy
            self._param_widgets.append(editor)

        self._output_ports = [
            PortItem(self, "output", i, port_model)
            for i, port_model in enumerate(self._node.outputs)
        ]

        # Preview widget (Display's pixmap, etc.) lives in its own
        # proxy below the IO rows; it has no port row of its own.
        preview = build_preview_widget(self._node)
        if preview is not None:
            self._preview_widget = preview
            self._preview_proxy = QGraphicsProxyWidget(self)
            self._preview_proxy.setWidget(preview)
        else:
            self._preview_proxy = None

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

        # ── IO area ────────────────────────────────────────────────────────────
        # Blender-style vertical split: outputs first (at top of body,
        # right-edge sockets), then inputs below (left-edge sockets,
        # with optional inline widgets). No per-row pairing.
        n_outputs = len(self._output_ports)
        n_inputs  = len(self._input_ports)
        io_height = (n_outputs + n_inputs) * self.PORT_ROW_HEIGHT

        # Preview (if any) gets a natural minimum and stretches to fill
        # whatever vertical space the user dragged the resize grip to.
        natural_preview_h = 0.0
        if self._preview_widget is not None:
            natural_preview_h = max(
                float(self._preview_widget.sizeHint().height()),
                100.0,  # don't collapse below something legible
            )
        gap_before_preview = self.PARAM_GAP if natural_preview_h > 0 else 0
        natural_body_h = (
            self.HEADER_HEIGHT
            + io_height
            + gap_before_preview
            + natural_preview_h
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

        # ── Reposition handles & ports ─────────────────────────────────────────
        self._close_button.setPos(
            self._width - self.PADDING - self.CLOSE_BUTTON_SIZE,
            (self.HEADER_HEIGHT - self.CLOSE_BUTTON_SIZE) / 2,
        )
        if self._skip_button is not None:
            self._skip_button.setPos(
                self.PADDING,
                (self.HEADER_HEIGHT - self.SKIP_BUTTON_SIZE) / 2,
            )
        self._resize_grip.setPos(
            self._width - self.RESIZE_GRIP_SIZE - 1,
            self._body_height - self.RESIZE_GRIP_SIZE - 1,
        )

        outputs_top = self._outputs_top()
        inputs_top = self._inputs_top()
        for i, port in enumerate(self._output_ports):
            port.setPos(self._width, outputs_top + (i + 0.5) * self.PORT_ROW_HEIGHT)
        for i, port in enumerate(self._input_ports):
            port.setPos(0.0, inputs_top + (i + 0.5) * self.PORT_ROW_HEIGHT)

        # ── Per-row inline param widgets ───────────────────────────────────────
        self._layout_param_widgets(inputs_top)

        # ── Preview widget below the IO rows ───────────────────────────────────
        if self._preview_widget is not None and self._preview_proxy is not None:
            preview_top = inputs_top + n_inputs * self.PORT_ROW_HEIGHT + gap_before_preview
            preview_h = self._body_height - preview_top - self.PADDING
            preview_h = max(natural_preview_h, preview_h)
            self._preview_widget.setFixedWidth(int(self._width - 2 * self.PADDING))
            self._preview_widget.setFixedHeight(int(preview_h))
            self._preview_proxy.setPos(self.PADDING, preview_top)

        self.refresh_all_links()
        self.update()

    def _layout_param_widgets(self, inputs_top: float) -> None:
        """Position each per-row inline param widget on its input port row.

        Widgets share two anchors: a common left X (one
        ``WIDGET_INSET`` past the longest input-row label, so labels
        never overlap the widget area), and the right edge of the
        node body (``width - WIDGET_INSET``). Each widget fills the
        whole strip in between — when the user drags the resize grip
        wider, widgets keep growing along with the node instead of
        stopping at their natural ``sizeHint`` and leaving ragged
        right edges. The minimum is the widget's own
        ``minimumSizeHint`` so a multi-element FilePathParamWidget
        still has room for its line-edit + buttons even on a narrow
        node; the natural ``sizeHint`` is no longer a cap.
        """
        if not self._param_widgets_by_row:
            return
        metrics = QFontMetricsF(QApplication.font())
        label_inset = PortItem.LABEL_OFFSET

        max_label_w = 0.0
        for row in self._param_widgets_by_row:
            label_w = (
                metrics.horizontalAdvance(self._input_ports[row].name)
                + label_inset
            )
            max_label_w = max(max_label_w, label_w)
        widget_x = max_label_w + self.WIDGET_INSET

        avail = self._width - widget_x - self.WIDGET_INSET
        for row, editor in self._param_widgets_by_row.items():
            proxy = self._param_proxies_by_row[row]
            min_w = float(editor.minimumSizeHint().width())
            widget_w = max(min_w, avail)
            widget_h = float(editor.sizeHint().height())
            y = inputs_top + row * self.PORT_ROW_HEIGHT + (self.PORT_ROW_HEIGHT - widget_h) / 2.0
            editor.setFixedSize(int(widget_w), int(widget_h))
            proxy.setPos(widget_x, y)

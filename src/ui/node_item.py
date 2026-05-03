from __future__ import annotations

from typing_extensions import override

from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, Qt, QTimer, Signal
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

from core.node_base import (
    Command,
    HeaderItem,
    NodeBase,
    Separator,
    SinkNodeBase,
    SourceNodeBase,
    TickBadge,
    Toggle,
)
from ui import clipboard
from ui.icons import paint_material_glyph
from ui.param_widgets import ParamWidgetBase, build_param_widget
from ui.port_item import PortItem
from ui.preview_widgets import build_preview_widget
from ui.theme import (
    BORDER_FROM_CATEGORY,
    FILTER_HEADER_COLOR,
    HEADER_AS_STRIP,
    NODE_BODY_COLOR,
    NODE_BORDER_COLOR,
    NODE_BORDER_SELECTED,
    NODE_GLOW_SELECTED_COLOR,
    NODE_GLOW_STROKES,
    NODE_PARAM_LABEL_COLOR,
    NODE_SKIPPED_HEADER_COLOR,
    NODE_TITLE_TEXT_COLOR,
    SINK_HEADER_COLOR,
    SOURCE_HEADER_COLOR,
)

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


class _SelectOnParamFocusFilter(QObject):
    """Promote the owning ``NodeItem`` to the only selected node when
    any descendant param widget gains keyboard focus.

    Without this, clicking inside a spinbox / line edit / combo on a
    node body gives that *widget* keyboard focus but does not select
    the *node* — any selection-driven panel keeps showing whatever was
    selected before, and the ``Delete`` key dispatcher in
    :meth:`FlowScene.keyPressEvent` (which branches on whether the
    focus item is a proxy widget) ends up targeting the wrong thing.
    Issue: #170

    Installed by :meth:`NodeItem._wire_param_focus_to_selection` on
    each ParamWidgetBase wrapper *and* every focusable child inside it
    (``QSpinBox``, ``QLineEdit``, etc.) — the wrapper is never
    keyboard-focusable itself, so a filter on it alone would never
    fire.
    """

    def __init__(self, owner_node_item: "NodeItem") -> None:
        # ``NodeItem`` is a ``QGraphicsItem`` (not a ``QObject``) so we
        # can't parent the filter to it the QObject way. Lifetime is
        # tied to the editor's ``_stjornhorn_focus_filter`` strong-ref
        # in :meth:`NodeItem._wire_param_focus_to_selection`.
        super().__init__()
        self._owner = owner_node_item

    @override
    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # type: ignore[override]
        if event.type() == QEvent.Type.FocusIn:
            scene = self._owner.scene()
            if scene is not None:
                # Focus is single-target — make the owner the only
                # selected item, even if it was already part of a
                # multi-selection. Skip the no-op case (owner is the
                # *only* selected item already) so we don't fire a
                # spurious selectionChanged that would re-trigger every
                # selection-driven panel update.
                others = [
                    item for item in scene.selectedItems()
                    if item is not self._owner
                ]
                if others or not self._owner.isSelected():
                    scene.clearSelection()
                    self._owner.setSelected(True)
        return False  # never consume — let Qt do its normal focus work.


class _ResizeGripItem(QGraphicsItem):
    """Bottom-right drag handle that resizes the owning node.

    Width is user-adjustable without upper bound; dragging narrower than
    :data:`NodeItem.MIN_WIDTH` clamps to the content-driven natural width.
    Vertical drag only changes the node's height when the node has a preview
    widget (otherwise content dictates height).
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


#: Width of the right-cluster gap, between adjacent header items.
HEADER_CLUSTER_GAP: float = 4.0
#: Side length of every clickable header button (close, skip, copy, …).
HEADER_BUTTON_SIZE: float = 14.0


class _HeaderButtonItem(QGraphicsItem):
    """Generic clickable button in a node's title bar.

    Renders the Material glyph of the underlying :class:`Command` or
    :class:`Toggle`. For a :class:`Toggle`, the button paints in an
    "active" style whenever ``is_active()`` returns True so the user
    sees the bound flag's state at a glance. Click invokes the
    handler; for a :class:`Command` whose handler returns a non-empty
    string, the result is copied to the system clipboard and a brief
    notification confirms the action.
    """

    SIZE: float = HEADER_BUTTON_SIZE
    Z_VALUE = 2

    def __init__(
        self, node_item: "NodeItem", item: Command | Toggle,
    ) -> None:
        super().__init__(parent=node_item)
        self._node_item = node_item
        self._item = item
        self._hovered = False
        self._pressed = False
        self.setZValue(self.Z_VALUE)
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setToolTip(item.tooltip)

    def boundingRect(self) -> QRectF:  # type: ignore[override]
        return QRectF(0, 0, self.SIZE, self.SIZE)

    def paint(self, painter: QPainter, option, widget=None) -> None:  # type: ignore[override]
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        active = isinstance(self._item, Toggle) and self._item.is_active()
        if self._hovered or self._pressed or active:
            painter.setPen(Qt.NoPen)
            alpha = 120 if active else 70
            painter.setBrush(QBrush(QColor(255, 255, 255, alpha)))
            painter.drawRoundedRect(self.boundingRect(), 2, 2)
        paint_material_glyph(
            painter,
            self._item.glyph,
            self.boundingRect(),
            color=NODE_TITLE_TEXT_COLOR,
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
            self.update()
            if self.boundingRect().contains(event.pos()):
                result = self._item.handler()
                if isinstance(self._item, Command):
                    clipboard.dispatch_command_result(result)
                if isinstance(self._item, Toggle):
                    # A toggle flips node state that affects what the
                    # flow does on the next run; emit ``param_changed``
                    # so auto-run and dirty markers behave the same as
                    # a regular param edit. Also forces a node repaint
                    # so the active-style background reflects the new
                    # ``is_active()`` value.
                    self._node_item.signals.param_changed.emit()
                self._node_item.update()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class _HeaderSeparatorItem(QGraphicsItem):
    """Thin vertical hairline drawn between adjacent header buttons.

    Pure visual divider — no interaction. Width is fixed; the
    rendered line is centered both horizontally inside that width and
    vertically inside the header height.
    """

    WIDTH: float = 6.0
    LINE_HEIGHT: float = 12.0
    Z_VALUE = 2

    def __init__(self, node_item: "NodeItem") -> None:
        super().__init__(parent=node_item)
        self.setZValue(self.Z_VALUE)

    def boundingRect(self) -> QRectF:  # type: ignore[override]
        return QRectF(0, 0, self.WIDTH, NodeItem.HEADER_HEIGHT)

    def paint(self, painter: QPainter, option, widget=None) -> None:  # type: ignore[override]
        x = self.WIDTH / 2.0
        y_top = (NodeItem.HEADER_HEIGHT - self.LINE_HEIGHT) / 2.0
        y_bot = y_top + self.LINE_HEIGHT
        color = QColor(NODE_TITLE_TEXT_COLOR)
        color.setAlpha(80)
        painter.setPen(QPen(color, 1.0))
        painter.drawLine(QPointF(x, y_top), QPointF(x, y_bot))


class _TickBadgeItem(QGraphicsItem):
    """Status text label in a node's title bar (e.g. a source's
    "100×" frame count).

    Re-queries the bound :class:`TickBadge`'s ``label`` callable on
    each paint so dynamic counts update without bookkeeping. An empty
    label collapses the bounding rect so the cluster has no gap when
    there's nothing to show.
    """

    Z_VALUE = 2

    def __init__(self, node_item: "NodeItem", item: TickBadge) -> None:
        super().__init__(parent=node_item)
        self._item = item
        self.setZValue(self.Z_VALUE)

    def _text(self) -> str:
        return self._item.label()

    def boundingRect(self) -> QRectF:  # type: ignore[override]
        text = self._text()
        if not text:
            return QRectF()
        w = QFontMetricsF(QApplication.font()).horizontalAdvance(text)
        return QRectF(0, 0, w, NodeItem.HEADER_HEIGHT)

    def paint(self, painter: QPainter, option, widget=None) -> None:  # type: ignore[override]
        text = self._text()
        if not text:
            return
        painter.setPen(QPen(QColor(255, 255, 255, 160)))
        painter.drawText(
            self.boundingRect(),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
            text,
        )


def _build_cluster_item(
    node_item: "NodeItem", spec: HeaderItem,
) -> QGraphicsItem:
    """Create the QGraphicsItem child that renders a single header item."""
    if isinstance(spec, (Command, Toggle)):
        return _HeaderButtonItem(node_item, spec)
    if isinstance(spec, Separator):
        return _HeaderSeparatorItem(node_item)
    if isinstance(spec, TickBadge):
        return _TickBadgeItem(node_item, spec)
    raise TypeError(f"Unsupported HeaderItem subtype: {type(spec).__name__}")


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
    RESIZE_GRIP_SIZE: float = 12.0
    # Header icon: square box (Material Icons render on a square em)
    # painted left of the title text. The gap separates the icon's
    # right edge from the title.
    HEADER_ICON_SIZE: float = 14.0
    HEADER_ICON_GAP: float = 5.0

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

        # Right-cluster items in left-to-right order. Built by
        # combining what the node declares (skip toggle, custom
        # actions, source-side tick badge) with the UI-side trailer
        # (separator + close). Positioned in ``_relayout`` via a
        # single right-to-left walk.
        cluster_specs: list[HeaderItem] = list(node.header_items())
        cluster_specs.append(Separator())
        cluster_specs.append(Command(
            glyph="close",
            tooltip="Delete this node",
            handler=self._close_handler,
        ))
        self._cluster_items: list[QGraphicsItem] = [
            _build_cluster_item(self, spec) for spec in cluster_specs
        ]
        self._resize_grip = _ResizeGripItem(self)

        self._build_ports()
        self._relayout()
        # Repaint the header badge whenever a constant param changes so the
        # tick count stays in sync with the current param values.
        self._signals.param_changed.connect(self.update)

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

    #: Worst-case outer-glow extent in scene pixels. Sized to cover
    #: any registered theme's :attr:`Theme.NODE_GLOW_STROKES` so
    #: ``boundingRect`` stays theme-independent (Qt's dirty-region
    #: tracking caches the rect; recomputing it on a theme swap would
    #: need a ``prepareGeometryChange`` we don't want to plumb).
    _BOUNDING_PAD: float = 8.0

    def boundingRect(self) -> QRectF:  # type: ignore[override]
        pad = self._BOUNDING_PAD
        return QRectF(-pad, -pad, self._width + 2 * pad, self._body_height + 2 * pad)

    def paint(self, painter: QPainter, option, widget=None) -> None:  # type: ignore[override]
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        body_rect = QRectF(0, 0, self._width, self._body_height)
        selected = self.isSelected()
        accent = self._header_color()
        # The per-category accent drives the border + glow on themes
        # that opted into :attr:`Theme.BORDER_FROM_CATEGORY` (neon
        # look). Themes with a solid coloured header strip (classic)
        # use a flat dark border instead — the strip already carries
        # the category. Selection always swaps to the single high-
        # contrast :data:`NODE_BORDER_SELECTED` so a selected node
        # stands out regardless of category.
        if selected:
            border_color = NODE_BORDER_SELECTED
            glow_color   = NODE_GLOW_SELECTED_COLOR
        elif BORDER_FROM_CATEGORY:
            border_color = accent
            glow_color   = accent
        else:
            border_color = NODE_BORDER_COLOR
            glow_color   = accent
        border_pen = QPen(border_color, 1.6 if selected else 1.2)

        # ── outer glow (themes opt in via NODE_GLOW_STROKES) ──
        for offset, alpha in NODE_GLOW_STROKES:
            glow = QColor(glow_color)
            glow.setAlpha(alpha)
            painter.setPen(QPen(glow, 1.0))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(
                body_rect.adjusted(-offset, -offset, offset, offset),
                self.CORNER_RADIUS + offset,
                self.CORNER_RADIUS + offset,
            )

        # ── body fill ──
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(NODE_BODY_COLOR))
        painter.drawRoundedRect(body_rect, self.CORNER_RADIUS, self.CORNER_RADIUS)

        # ── header band ──
        if HEADER_AS_STRIP:
            # Solid coloured header strip (classic). Rendered as a
            # path with rounded top corners only so it tucks under
            # the body's rounded outline. Drawn before the border so
            # the border's stroke clips the strip's edges cleanly.
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(accent))
            painter.drawPath(self._header_path())
        else:
            # Thin category-accent divider under the title row
            # (neon). Keeps the kind readable when the rim flips to
            # the selection accent.
            divider_color = QColor(accent)
            divider_color.setAlpha(140)
            painter.setPen(QPen(divider_color, 1.0))
            painter.drawLine(
                QPointF(self.PADDING, self.HEADER_HEIGHT),
                QPointF(self._width - self.PADDING, self.HEADER_HEIGHT),
            )

        # ── border (stroked last so nothing covers it) ──
        painter.setPen(border_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(body_rect, self.CORNER_RADIUS, self.CORNER_RADIUS)

        # ── header icon (declared by the node class via HEADER_ICON) ──
        icon_name = self._node.HEADER_ICON
        if icon_name:
            ix = self._header_icon_x()
            iy = (self.HEADER_HEIGHT - self.HEADER_ICON_SIZE) / 2
            paint_material_glyph(
                painter,
                icon_name,
                QRectF(ix, iy, self.HEADER_ICON_SIZE, self.HEADER_ICON_SIZE),
                color=QColor(255, 255, 255, 200),
            )

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

        # Constants block: italic captions left-aligned, label
        # truncated where the inline widget starts. No socket dot —
        # constants are not driveable from upstream.
        constants_top = self._constants_top()
        if self._constant_widgets_by_row:
            italic_font = painter.font()
            italic_font.setItalic(True)
            painter.save()
            painter.setFont(italic_font)
            for row, _editor in self._constant_widgets_by_row.items():
                y = constants_top + (row + 0.5) * self.PORT_ROW_HEIGHT
                proxy = self._constant_proxies_by_row[row]
                label_right = proxy.pos().x() - self.WIDGET_INSET
                painter.drawText(
                    QRectF(label_inset, y - self.PORT_ROW_HEIGHT / 2,
                           max(0.0, label_right - label_inset),
                           self.PORT_ROW_HEIGHT),
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                    self._node.params[row].name,
                )
            painter.restore()

        # Inputs follow below; rows with a widget truncate the label.
        # Skip rows past the visible-input count so labels match the
        # body geometry on nodes that opt into ``SHOW_ONLY_USED_INPUTS``.
        inputs_top = self._inputs_top()
        n_visible_inputs = self._visible_input_count()
        for i, port in enumerate(self._input_ports):
            if i >= n_visible_inputs:
                break
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

        # Selection and keyboard focus must stay in lock-step: when
        # this node loses selection, drop focus from any of its
        # embedded param widgets that still hold it. Otherwise the
        # user's next keystroke would edit a control on a node that
        # no longer "looks" selected. Issue: #170
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            if not bool(value):
                self._clear_param_widget_focus()

        return super().itemChange(change, value)

    def _wire_param_focus_to_selection(self, editor: QWidget) -> None:
        """Install a focus filter that selects this NodeItem when the
        embedded *editor* (or any focusable widget inside it) gains
        keyboard focus.

        Filters every keyboard-focusable descendant rather than the
        wrapper alone — ParamWidgetBase wrappers are
        ``WA_TranslucentBackground`` containers whose actual focusable
        controls are children (``QSpinBox``, ``QLineEdit``,
        ``QComboBox``, ``QCheckBox``). A filter on the wrapper alone
        would never see a ``FocusIn`` event. Issue: #170
        """
        filt = _SelectOnParamFocusFilter(self)
        editor.installEventFilter(filt)
        for child in editor.findChildren(QWidget):
            child.installEventFilter(filt)
        # Hold a strong reference on the editor so the filter QObject
        # outlives the local — without this the filter is GC'd
        # immediately after this method returns and Qt silently drops
        # the installation.
        editor._stjornhorn_focus_filter = filt  # type: ignore[attr-defined]

    def _clear_param_widget_focus(self) -> None:
        """Drop keyboard focus from every embedded param widget on
        this node that currently has it.

        Called from :meth:`itemChange` on a selection→unselected
        transition. Iterates the param-port editors, the constant-
        param editors and the preview proxy; each may host either a
        single focusable control or a layout of several
        (FilePathParamWidget has line-edit + two buttons), so we ask
        Qt for the actual ``focusWidget()`` inside the wrapper rather
        than guessing. Issue: #170
        """
        proxies: list[QGraphicsProxyWidget] = []
        proxies.extend(self._param_proxies_by_row.values())
        proxies.extend(self._constant_proxies_by_row.values())
        if self._preview_proxy is not None:
            proxies.append(self._preview_proxy)

        for proxy in proxies:
            wrapper = proxy.widget()
            if wrapper is None:
                continue
            focused = wrapper.focusWidget()
            if focused is not None:
                focused.clearFocus()
            elif wrapper.hasFocus():
                wrapper.clearFocus()

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
        """Horizontal space reserved on the header's right edge for
        the title-bar cluster (tick badge / actions / separator /
        close), the right padding, and a leading gap between the title
        text and the leftmost cluster item.
        """
        widths = [
            it.boundingRect().width()
            for it in self._cluster_items
            if it.boundingRect().width() > 0
        ]
        if not widths:
            return self.PADDING
        cluster_w = sum(widths) + (len(widths) - 1) * HEADER_CLUSTER_GAP
        # PADDING on the right edge + a separating gap between the
        # title's right edge and the leftmost cluster item.
        return cluster_w + self.PADDING + HEADER_CLUSTER_GAP

    def _title_left(self) -> float:
        """X offset where the title text starts, just past the
        node-class header icon (when present)."""
        offset = self.PADDING
        if self._node.HEADER_ICON:
            offset += self.HEADER_ICON_SIZE + self.HEADER_ICON_GAP
        return offset

    def _header_icon_x(self) -> float:
        """X offset of the header icon's left edge — flush with
        :attr:`PADDING`, with the title text directly to its right."""
        return self.PADDING

    def _close_handler(self) -> None:
        """Handler for the auto-injected close :class:`Command`.

        Defers the actual scene removal so we don't delete ourselves
        while still inside the click event handler chain.
        """
        scene = self.scene()
        if scene is not None and hasattr(scene, "remove_node_item"):
            QTimer.singleShot(0, lambda: scene.remove_node_item(self))

    def _header_path(self) -> QPainterPath:
        """Path for the header strip: top corners rounded, bottom
        corners square. Used by themes that opt into the classic
        solid coloured header (``Theme.HEADER_AS_STRIP``)."""
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

    def _constants_top(self) -> float:
        """Y of the first constant-param row — sits below the
        output block, above the input block."""
        return self.HEADER_HEIGHT + len(self._output_ports) * self.PORT_ROW_HEIGHT

    def _inputs_top(self) -> float:
        """Y of the first input row — inputs sit below the output
        block and the (optional) constants block. Param-style inputs
        carry an inline widget on the same row as their socket dot."""
        return self._constants_top() + len(self._constant_widgets_by_row) * self.PORT_ROW_HEIGHT

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
        # Both inline-port widgets and constant widgets share the
        # same widget-X anchor (see ``_layout_param_widgets``) so the
        # natural-width budget needs to fit the longest label + widest
        # widget-min across BOTH groups combined.
        all_label_widths: list[float] = []
        all_widget_mins: list[float] = []
        for i in self._param_widgets_by_row:
            all_label_widths.append(metrics.horizontalAdvance(self._input_ports[i].name))
        for row in self._constant_widgets_by_row:
            all_label_widths.append(metrics.horizontalAdvance(self._node.params[row].name))
        for editor in self._param_widgets_by_row.values():
            all_widget_mins.append(float(editor.minimumSizeHint().width()))
        for editor in self._constant_widgets_by_row.values():
            all_widget_mins.append(float(editor.minimumSizeHint().width()))
        if all_label_widths and all_widget_mins:
            row_need = (
                label_inset + max(all_label_widths)
                + 2 * self.WIDGET_INSET
                + max(all_widget_mins)
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
            self._wire_param_focus_to_selection(editor)
            self._param_widgets_by_row[i] = editor
            self._param_proxies_by_row[i] = proxy
            self._param_widgets.append(editor)

        self._output_ports = [
            PortItem(self, "output", i, port_model)
            for i, port_model in enumerate(self._node.outputs)
        ]

        # Constant params (NodeParam — sources / sinks declare these
        # for config that's not driveable from upstream). They render
        # between the output and input port rows of the node body
        # with the same widget classes the inline-port editors use,
        # but with an italic caption (painted in :meth:`paint`) and
        # no socket dot. Indexed by row inside the constants block.
        self._constant_widgets_by_row: dict[int, ParamWidgetBase] = {}
        self._constant_proxies_by_row: dict[int, QGraphicsProxyWidget] = {}
        for row, param in enumerate(self._node.params):
            editor = build_param_widget(self._node, param)
            if editor is None:
                continue
            editor.value_changed.connect(
                lambda _v: self._signals.param_changed.emit()
            )
            proxy = QGraphicsProxyWidget(self)
            proxy.setWidget(editor)
            self._wire_param_focus_to_selection(editor)
            self._constant_widgets_by_row[row] = editor
            self._constant_proxies_by_row[row] = proxy
            self._param_widgets.append(editor)

        # Preview widget (Display's pixmap, etc.) lives in its own
        # proxy below the IO rows; it has no port row of its own.
        preview = build_preview_widget(self._node)
        if preview is not None:
            self._preview_widget = preview
            self._preview_proxy = QGraphicsProxyWidget(self)
            self._preview_proxy.setWidget(preview)
        else:
            self._preview_proxy = None

    def _visible_input_count(self) -> int:
        """Return how many input rows the body should render.

        For nodes that opt into ``SHOW_ONLY_USED_INPUTS`` the editor
        shows everything up to the last connected port plus one empty
        "to-be-wired" tail (so the user sees there's another slot
        available). Other nodes render every input port — same
        behaviour they always had.
        """
        all_inputs = self._input_ports
        if not getattr(self._node, "SHOW_ONLY_USED_INPUTS", False):
            return len(all_inputs)
        last_connected = -1
        for i, port_item in enumerate(all_inputs):
            if port_item.model.upstream is not None:
                last_connected = i
        # Show one row beyond the last connection — capped at the pool
        # size — and never less than one so the node has at least one
        # visible input row.
        return min(len(all_inputs), max(1, last_connected + 2))

    def refresh_input_visibility(self) -> None:
        """Re-evaluate which input rows are visible.

        Called by :class:`FlowScene` after a connect / disconnect
        affecting any input on this node so the body can grow or
        shrink. Cheap — only flips ``setVisible`` on PortItems and
        their per-row inline widgets and re-runs :meth:`_relayout`.
        """
        self._relayout()

    def _relayout(self) -> None:
        """Recompute width / body height and place every child item.

        Honours user-chosen overrides (via :meth:`apply_user_size`) and
        otherwise falls back to content-driven natural dimensions.
        Callable repeatedly — called on construction and every resize.
        """
        self.prepareGeometryChange()

        # ── Width ──────────────────────────────────────────────────────────────
        # The natural width is the floor: it's exactly the size where
        # the longest label + widest inline widget fit without
        # overflowing, so dragging the resize grip narrower can't
        # shrink the node past it (otherwise widget right edges spill
        # past the body). The grip can still grow the node up to
        # ``MAX_USER_WIDTH``.
        natural_w = self._compute_width()
        if self._user_width is not None:
            self._width = max(natural_w, self._user_width)
        else:
            self._width = natural_w

        # ── IO area ────────────────────────────────────────────────────────────
        # Blender-style vertical split: outputs first (at top of body),
        # then constant params (sources / sinks register these via
        # ``_add_param``; rendered with italic captions, no socket
        # dots), then input ports (left-edge sockets, with optional
        # inline widgets on each row).
        n_outputs = len(self._output_ports)
        # ``n_inputs`` is the *visible* count — for nodes that opt into
        # ``SHOW_ONLY_USED_INPUTS`` it tracks "last connected + 1" so
        # the body grows and shrinks with use; for everyone else it's
        # the full input pool size. Hidden PortItems and their per-row
        # widgets are toggled via ``setVisible`` further down.
        n_inputs  = self._visible_input_count()
        n_consts  = len(self._constant_widgets_by_row)
        io_height = (n_outputs + n_consts + n_inputs) * self.PORT_ROW_HEIGHT

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
        # Right-cluster layout: walk the cluster items right-to-left,
        # placing each just inside the previous one. Items whose
        # bounding rect is empty (e.g. a tick badge with no current
        # count) collapse without leaving a gap.
        x = self._width - self.PADDING
        first = True
        for item in reversed(self._cluster_items):
            br = item.boundingRect()
            if br.width() == 0:
                continue
            if not first:
                x -= HEADER_CLUSTER_GAP
            x -= br.width()
            item.setPos(x, (self.HEADER_HEIGHT - br.height()) / 2)
            first = False
        self._resize_grip.setPos(
            self._width - self.RESIZE_GRIP_SIZE - 1,
            self._body_height - self.RESIZE_GRIP_SIZE - 1,
        )

        outputs_top = self._outputs_top()
        inputs_top = self._inputs_top()
        for i, port in enumerate(self._output_ports):
            port.setPos(self._width, outputs_top + (i + 0.5) * self.PORT_ROW_HEIGHT)
        for i, port in enumerate(self._input_ports):
            visible = i < n_inputs
            port.setVisible(visible)
            if visible:
                port.setPos(0.0, inputs_top + (i + 0.5) * self.PORT_ROW_HEIGHT)
            # Per-row inline widget (if any) follows the same visibility.
            proxy = self._param_proxies_by_row.get(i)
            if proxy is not None:
                proxy.setVisible(visible)

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
        """Position each editable widget — both the inline-port
        widgets sitting on input rows and the constant-param widgets
        in the constants block — along a shared left/right anchor.

        The left anchor is one ``WIDGET_INSET`` past the longest
        label across BOTH groups (port labels + constant captions),
        so widgets in the constants block line up with widgets on
        input rows. The right anchor is ``width - WIDGET_INSET`` —
        widgets fill the whole strip, growing with the node on
        resize. Vertical position is per-row (constant rows in the
        constants block, input-port widgets in the input block).
        """
        metrics = QFontMetricsF(QApplication.font())
        label_inset = PortItem.LABEL_OFFSET

        # Compute a single widget-X that fits past the longest label
        # in either block. Constants have no socket dot, so their
        # caption inset is also ``label_inset`` for consistent
        # horizontal alignment with the port-row labels.
        max_label_w = 0.0
        for row in self._param_widgets_by_row:
            max_label_w = max(
                max_label_w,
                metrics.horizontalAdvance(self._input_ports[row].name) + label_inset,
            )
        for row, _editor in self._constant_widgets_by_row.items():
            param = self._node.params[row]
            max_label_w = max(
                max_label_w,
                metrics.horizontalAdvance(param.name) + label_inset,
            )
        if max_label_w == 0.0:
            return

        widget_x = max_label_w + self.WIDGET_INSET
        avail = self._width - widget_x - self.WIDGET_INSET

        # Constants block: one row per constant, starting at
        # ``_constants_top()``.
        constants_top = self._constants_top()
        for row, editor in self._constant_widgets_by_row.items():
            proxy = self._constant_proxies_by_row[row]
            min_w = float(editor.minimumSizeHint().width())
            widget_w = max(min_w, avail)
            widget_h = float(editor.sizeHint().height())
            y = constants_top + row * self.PORT_ROW_HEIGHT + (self.PORT_ROW_HEIGHT - widget_h) / 2.0
            editor.setFixedSize(int(widget_w), int(widget_h))
            proxy.setPos(widget_x, y)

        # Input block: widgets sit on the same row as their port dot.
        for row, editor in self._param_widgets_by_row.items():
            proxy = self._param_proxies_by_row[row]
            min_w = float(editor.minimumSizeHint().width())
            widget_w = max(min_w, avail)
            widget_h = float(editor.sizeHint().height())
            y = inputs_top + row * self.PORT_ROW_HEIGHT + (self.PORT_ROW_HEIGHT - widget_h) / 2.0
            editor.setFixedSize(int(widget_w), int(widget_h))
            proxy.setPos(widget_x, y)

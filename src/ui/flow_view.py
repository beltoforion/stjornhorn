from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QPoint, QRectF, Qt
from PySide6.QtGui import QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QGraphicsView

from ui.node_list import NODE_LIST_MIME_TYPE
from ui.theme import CANVAS_BACKGROUND_COLOR, CANVAS_GRID_COLOR

if TYPE_CHECKING:
    from ui.flow_scene import FlowScene

logger = logging.getLogger(__name__)


class FlowView(QGraphicsView):
    """Zoomable / pannable view hosting a :class:`FlowScene`.

    - Scroll wheel: zoom around the cursor (0.2× – 5×).
    - Middle-mouse drag: pan (delta-based, no drag-mode swap).
    - Left-click empty space: rubber-band selection.
    - Accepts drops with MIME type ``NODE_LIST_MIME_TYPE`` carrying a
      serialised NodeEntry descriptor; the scene instantiates and places
      the node under the cursor.
    """

    _ZOOM_STEP: float = 1.15
    _ZOOM_MIN:  float = 0.2
    _ZOOM_MAX:  float = 5.0

    # Fit-to-contents padding ratios. The view zooms to a tight rect
    # around the layout (so the graph fills the viewport), but the
    # scene rect is set wider so the user has room to pan past the
    # layout edges without hitting the scroll-bar end-stop.
    _FIT_VIEW_PADDING:  float = 0.05
    _FIT_SCENE_PADDING: float = 0.33

    def __init__(self, scene: FlowScene) -> None:
        super().__init__(scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setAcceptDrops(True)
        self.setBackgroundBrush(CANVAS_BACKGROUND_COLOR)

        self._panning: bool = False
        self._pan_last: QPoint | None = None

        self._screen_hooks_connected: bool = False
        self._connect_screen_hooks()

    # ── Screen-topology logging ────────────────────────────────────────────────
    #
    # Record the initial screen layout and every subsequent change Qt reports
    # so we can correlate render glitches with display events in post-mortems.
    # No recovery logic lives here — we've seen blank-node reports from brief
    # OS-initiated screen blackouts (Linux Mint / X11 / NVIDIA) that don't
    # trigger any of these Qt signals, so relying on them to heal the UI
    # would be misleading.

    def _connect_screen_hooks(self) -> None:
        if self._screen_hooks_connected:
            return
        app = QGuiApplication.instance()
        if app is None:
            return
        app.screenAdded.connect(self._on_screen_added)
        app.screenRemoved.connect(self._on_screen_removed)
        app.primaryScreenChanged.connect(self._on_primary_screen_changed)
        self._screen_hooks_connected = True
        self._log_screen_layout("initial")

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        window = self.window()
        handle = window.windowHandle() if window is not None else None
        if handle is not None:
            try:
                handle.screenChanged.connect(
                    self._on_window_screen_changed,
                    Qt.ConnectionType.UniqueConnection,
                )
            except (RuntimeError, TypeError):
                # Already connected, or handle has no such signal on this platform.
                pass

    def changeEvent(self, event) -> None:  # type: ignore[override]
        if event.type() == QEvent.Type.ScreenChangeInternal:
            logger.info("FlowView received ScreenChangeInternal")
        super().changeEvent(event)

    def _on_screen_added(self, screen) -> None:
        logger.info("Screen added: %s", screen.name() if screen is not None else "<none>")
        self._log_screen_layout("after add")

    def _on_screen_removed(self, screen) -> None:
        logger.info("Screen removed: %s", screen.name() if screen is not None else "<none>")
        self._log_screen_layout("after remove")

    def _on_primary_screen_changed(self, screen) -> None:
        logger.info(
            "Primary screen changed → %s",
            screen.name() if screen is not None else "<none>",
        )
        self._log_screen_layout("after primary change")

    def _on_window_screen_changed(self, screen) -> None:
        logger.info(
            "Main window moved to screen: %s",
            screen.name() if screen is not None else "<none>",
        )

    def _log_screen_layout(self, reason: str) -> None:
        app = QGuiApplication.instance()
        if app is None:
            return
        screens = app.screens()
        primary = app.primaryScreen()
        logger.info(
            "Screen layout (%s): %d screen(s), primary=%s",
            reason,
            len(screens),
            primary.name() if primary is not None else "<none>",
        )
        for i, screen in enumerate(screens):
            geom = screen.geometry()
            logger.info(
                "  [%d] %s  geom=%dx%d+%d+%d  dpr=%.2f  refresh=%.1fHz",
                i,
                screen.name(),
                geom.width(),
                geom.height(),
                geom.x(),
                geom.y(),
                screen.devicePixelRatio(),
                screen.refreshRate(),
            )

    # ── Zoom ───────────────────────────────────────────────────────────────────

    def wheelEvent(self, event) -> None:  # type: ignore[override]
        factor = self._ZOOM_STEP if event.angleDelta().y() > 0 else 1.0 / self._ZOOM_STEP
        new_scale = self.transform().m11() * factor
        if new_scale < self._ZOOM_MIN or new_scale > self._ZOOM_MAX:
            return
        self.scale(factor, factor)


    def fit_to_contents(self) -> None:
        """Zoom the view so the layout fills the viewport with a small
        margin, while leaving a wider scene rect around it for panning.

        Two rects, two purposes:
          * **view rect** (layout + ``_FIT_VIEW_PADDING``) — passed to
            ``fitInView`` so the graph reads as "filling" the viewport.
          * **scene rect** — sized so that on each axis there's at
            least ``_FIT_SCENE_PADDING`` of layout-relative pan
            margin *beyond the post-fit visible area*. Naively
            taking ``layout + 20%`` collapses to "no pan room" on
            the non-fit axis when the viewport aspect mismatches
            the layout, because KeepAspectRatio leaves slack there
            that already exceeds the layout bounds.

        The bounding rect is computed from structural items only — node
        bodies and backdrops — *not* from wires. ``LinkItem`` is a cubic
        Bezier whose control points extend the path's bounding rect
        beyond the straight line between its ports; if wires curve more
        on one side of the graph, that asymmetry shifts the canvas
        centre and the visible node cluster ends up off-centre even
        though the rect is technically centered. Anchoring on structural
        items makes Fit reflect the layout the user is actually
        positioning. Idempotent on repeat calls; no-op on empty scenes.

        Issue: #191
        """
        from ui.backdrop_item import BackdropItem
        from ui.node_item import NodeItem

        scene = self.scene()
        rect: QRectF | None = None
        for item in scene.items():
            if isinstance(item, (NodeItem, BackdropItem)):
                item_rect = item.sceneBoundingRect()
                rect = item_rect if rect is None else rect.united(item_rect)
        if rect is None or rect.isEmpty():
            return

        view_pad_x = rect.width() * self._FIT_VIEW_PADDING
        view_pad_y = rect.height() * self._FIT_VIEW_PADDING
        view_rect = rect.adjusted(-view_pad_x, -view_pad_y, view_pad_x, view_pad_y)

        # Derive the post-fit scale up front so we know the visible
        # scene area. With KeepAspectRatio, fitInView fills one axis
        # exactly and leaves slack on the other — that slack inflates
        # the visible scene rect on the non-fit axis well past
        # ``view_rect``. If we sized ``scene_rect`` only relative to
        # the layout, the slack would eat into the pan margin on that
        # axis (typically: wide layout in a wide viewport → almost no
        # vertical pan room). Compute the visible rect explicitly and
        # ensure ``scene_rect`` extends ``_FIT_SCENE_PADDING`` *beyond
        # the visible area* on each axis.
        viewport_size = self.viewport().size()
        sx = viewport_size.width() / view_rect.width()
        sy = viewport_size.height() / view_rect.height()
        fit_scale = min(min(sx, sy), self._ZOOM_MAX)
        visible_w = viewport_size.width() / fit_scale
        visible_h = viewport_size.height() / fit_scale

        pan_x = rect.width() * self._FIT_SCENE_PADDING
        pan_y = rect.height() * self._FIT_SCENE_PADDING
        half_w = max(rect.width(), visible_w) / 2 + pan_x
        half_h = max(rect.height(), visible_h) / 2 + pan_y
        center = rect.center()
        scene_rect = QRectF(
            center.x() - half_w, center.y() - half_h, 2 * half_w, 2 * half_h,
        )

        scene.setSceneRect(scene_rect)
        self.fitInView(view_rect, Qt.AspectRatioMode.KeepAspectRatio)
        # If the layout is small enough that fitInView zoomed past our
        # max, clamp the scale — but keep the layout centered. The old
        # implementation called resetTransform() here, which dropped the
        # view back to 1:1 *without* re-centering, so small graphs ended
        # up wherever the scroll bars happened to be. Issue: #191
        scale = self.transform().m11()
        if scale > self._ZOOM_MAX:
            self.resetTransform()
            self.scale(self._ZOOM_MAX, self._ZOOM_MAX)
        self.centerOn(view_rect.center())

    def reset_zoom(self) -> None:
        """Reset the view transform to the default 1:1 scale."""
        self.resetTransform()

    # ── Middle-mouse pan ───────────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_last = event.position().toPoint()
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._panning and self._pan_last is not None:
            now = event.position().toPoint()
            delta = now - self._pan_last
            self._pan_last = now
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.MiddleButton and self._panning:
            self._panning = False
            self._pan_last = None
            self.viewport().unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # ── Grid background ────────────────────────────────────────────────────────

    def drawBackground(self, painter, rect) -> None:  # type: ignore[override]
        super().drawBackground(painter, rect)
        grid = 32
        pen = QPen(CANVAS_GRID_COLOR, 0)
        painter.setPen(pen)
        left = int(rect.left()) - (int(rect.left()) % grid)
        top = int(rect.top()) - (int(rect.top()) % grid)
        x = left
        while x < rect.right():
            painter.drawLine(x, int(rect.top()), x, int(rect.bottom()))
            x += grid
        y = top
        while y < rect.bottom():
            painter.drawLine(int(rect.left()), y, int(rect.right()), y)
            y += grid

    # ── Drops from the palette ─────────────────────────────────────────────────

    def dragEnterEvent(self, event) -> None:  # type: ignore[override]
        if event.mimeData().hasFormat(NODE_LIST_MIME_TYPE):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # type: ignore[override]
        if event.mimeData().hasFormat(NODE_LIST_MIME_TYPE):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:  # type: ignore[override]
        mime = event.mimeData()
        if not mime.hasFormat(NODE_LIST_MIME_TYPE):
            super().dropEvent(event)
            return
        try:
            payload = bytes(mime.data(NODE_LIST_MIME_TYPE)).decode("utf-8")
            data = json.loads(payload)
        except Exception:
            logger.exception("Malformed %s payload", NODE_LIST_MIME_TYPE)
            return

        from core.node_registry import NodeEntry
        entry = NodeEntry(
            display_name=data.get("display_name", ""),
            category=data.get("category", ""),
            # NodeList started carrying ``section`` in its drag payload in
            # #52; default to the category so drops from stale payloads
            # still instantiate cleanly instead of raising TypeError.
            section=data.get("section", data.get("category", "")),
            module=data["module"],
            class_name=data["class_name"],
        )

        scene_pos = self.mapToScene(event.position().toPoint())
        scene: FlowScene = self.scene()  # type: ignore[assignment]
        if scene is not None:
            scene.instantiate_and_add(entry, scene_pos)
        event.acceptProposedAction()

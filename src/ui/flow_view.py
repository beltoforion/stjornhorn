from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QMarginsF, QPoint, Qt
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
        """Zoom and scroll so that all scene items are visible."""
        rect = self.scene().itemsBoundingRect()
        if rect.isNull():
            return
        # Add a small margin so nodes don't touch the viewport edges.
        rect = rect.marginsAdded(QMarginsF(40, 40, 40, 40))
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        # Clamp if fitInView zoomed beyond our limits.
        scale = self.transform().m11()
        if scale > self._ZOOM_MAX:
            self.reset_zoom()

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

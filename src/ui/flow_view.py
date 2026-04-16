from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QMarginsF, QPoint, Qt
from PySide6.QtGui import QPainter, QPen
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

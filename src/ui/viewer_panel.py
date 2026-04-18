from __future__ import annotations

import logging

import cv2
import numpy as np
from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.io_data import IoDataType
from core.node_base import NodeBase
from ui.theme import STATUS_FAIL_COLOR, STATUS_MUTED_COLOR

logger = logging.getLogger(__name__)

# Images larger than this on either dimension are downsampled before
# being converted to a QPixmap. Keeps memory sane for 4K inputs.
_MAX_DIM: int = 1024


class ViewerPanel(QWidget):
    """Scrollable panel ("Output Inspector") that renders every image output of a node.

    ``show(node)`` wipes the panel and re-populates it with one labelled
    :class:`QLabel` + :class:`QPixmap` pair per ``IoDataType.IMAGE``
    output port that has cached data. Non-image outputs and empty ports
    are represented by a muted placeholder label so the layout always
    reflects the node's output topology.

    Each image is always scaled to the current viewport width so the
    inspector never needs horizontal scrolling. Resize events re-scale
    the cached pixmaps in place.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_node: NodeBase | None = None
        # (label, original-pixmap) pairs kept so we can rescale on resize
        # without re-running the node pipeline.
        self._image_labels: list[tuple[QLabel, QPixmap]] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        outer.addWidget(self._scroll)

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(8, 8, 8, 8)
        self._content_layout.setSpacing(8)
        self._content_layout.addStretch(1)
        self._scroll.setWidget(self._content)

        # Viewport width drives the image scale, so react to its resize events
        # (the scrollbar appearing/disappearing changes the viewport width
        # without resizing this outer widget).
        self._scroll.viewport().installEventFilter(self)

        self._placeholder("(select a node to view its output)", muted=True)

    # ── Public API ─────────────────────────────────────────────────────────────

    def show_node(self, node: NodeBase | None) -> None:
        """Render every image output of ``node`` in the panel."""
        self._current_node = node
        self._clear()

        if node is None:
            self._placeholder("(select a node to view its output)", muted=True)
            return
        if not node.outputs:
            self._placeholder(f"{node.display_name}: node has no outputs", muted=True)
            return

        for port in node.outputs:
            if IoDataType.IMAGE not in port.emits:
                self._placeholder(f"{port.name}: (non-image output)", muted=True)
                continue

            data = port.last_emitted
            if data is None or data.type != IoDataType.IMAGE:
                self._placeholder(f"{port.name}: (no data — click Run)", muted=True)
                continue

            try:
                self._render_image(port.name, data.image)
            except Exception:
                logger.exception("Viewer failed to render port '%s'", port.name)
                self._placeholder(f"{port.name}: (render error — see log)", error=True)

    @property
    def current_node(self) -> NodeBase | None:
        """The node currently displayed in the viewer, or ``None``."""
        return self._current_node

    def refresh(self) -> None:
        """Re-render the currently-shown node (called after Run)."""
        self.show_node(self._current_node)

    # ── Internals ──────────────────────────────────────────────────────────────

    def _clear(self) -> None:
        while self._content_layout.count() > 0:
            item = self._content_layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._image_labels.clear()
        self._content_layout.addStretch(1)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # type: ignore[override]
        if obj is self._scroll.viewport() and event.type() == QEvent.Type.Resize:
            self._rescale_images()
        return super().eventFilter(obj, event)

    def _available_width(self) -> int:
        """Width available to an image inside the scroll viewport."""
        vp = self._scroll.viewport().width()
        m = self._content_layout.contentsMargins()
        return max(1, vp - m.left() - m.right())

    def _scaled_pixmap(self, original: QPixmap) -> QPixmap:
        w = self._available_width()
        if w <= 0 or original.isNull() or original.width() == 0:
            return original
        return original.scaledToWidth(w, Qt.TransformationMode.SmoothTransformation)

    def _rescale_images(self) -> None:
        for label, original in self._image_labels:
            label.setPixmap(self._scaled_pixmap(original))

    def _placeholder(self, text: str, *, muted: bool = False, error: bool = False) -> None:
        label = QLabel(text)
        if error:
            label.setStyleSheet(f"color: rgb({STATUS_FAIL_COLOR.red()},"
                                f" {STATUS_FAIL_COLOR.green()},"
                                f" {STATUS_FAIL_COLOR.blue()});")
        elif muted:
            label.setStyleSheet(f"color: rgb({STATUS_MUTED_COLOR.red()},"
                                f" {STATUS_MUTED_COLOR.green()},"
                                f" {STATUS_MUTED_COLOR.blue()});")
        self._content_layout.insertWidget(self._content_layout.count() - 1, label)

    def _render_image(self, port_name: str, image: np.ndarray) -> None:
        rgba = self._to_rgba(image)
        h, w = rgba.shape[:2]

        # Downsample oversized images before uploading to a QPixmap.
        max_dim = max(h, w)
        if max_dim > _MAX_DIM:
            scale = _MAX_DIM / max_dim
            new_w = max(1, int(w * scale))
            new_h = max(1, int(h * scale))
            rgba = cv2.resize(rgba, (new_w, new_h), interpolation=cv2.INTER_AREA)
            h, w = rgba.shape[:2]

        rgba = np.ascontiguousarray(rgba)
        qimg = QImage(rgba.data, w, h, rgba.strides[0], QImage.Format.Format_RGBA8888).copy()
        pixmap = QPixmap.fromImage(qimg)

        title = QLabel(f"{port_name}  ({w}×{h})")
        title.setStyleSheet(f"color: rgb({STATUS_MUTED_COLOR.red()},"
                            f" {STATUS_MUTED_COLOR.green()},"
                            f" {STATUS_MUTED_COLOR.blue()});")
        self._content_layout.insertWidget(self._content_layout.count() - 1, title)

        image_label = QLabel()
        image_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        image_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        image_label.setPixmap(self._scaled_pixmap(pixmap))
        self._image_labels.append((image_label, pixmap))
        self._content_layout.insertWidget(self._content_layout.count() - 1, image_label)

    @staticmethod
    def _to_rgba(image: np.ndarray) -> np.ndarray:
        """Coerce a NumPy image to a uint8 RGBA array (H, W, 4)."""
        if image.dtype != np.uint8:
            image = np.clip(image, 0, 255).astype(np.uint8)
        if image.ndim == 2:
            return cv2.cvtColor(image, cv2.COLOR_GRAY2RGBA)
        if image.shape[2] == 3:
            return cv2.cvtColor(image, cv2.COLOR_BGR2RGBA)
        if image.shape[2] == 4:
            return cv2.cvtColor(image, cv2.COLOR_BGRA2RGBA)
        raise ValueError(f"Unsupported image shape {image.shape}")

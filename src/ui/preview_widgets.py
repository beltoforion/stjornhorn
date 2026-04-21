from __future__ import annotations

import logging

import numpy as np
from typing_extensions import override

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from core.node_base import NodeBase
from nodes.filters.display import Display

logger = logging.getLogger(__name__)


class _PreviewWidgetBase(QWidget):
    """Base class for inline preview widgets embedded in a NodeItem body.

    A preview widget is attached to a node and renders whatever that
    node wants to show live — typically the most recent frame it
    processed. Subclasses must wire themselves to the node during
    :meth:`__init__` (e.g. by registering a callback) and marshal any
    worker-thread events back to the UI thread via a queued
    :class:`~PySide6.QtCore.Signal`.
    """

    def __init__(self, node: NodeBase) -> None:
        if type(self) is _PreviewWidgetBase:
            raise TypeError("_PreviewWidgetBase cannot be instantiated directly")
        super().__init__()
        self._node = node


class DisplayPreview(_PreviewWidgetBase):
    """Inline preview for :class:`~nodes.filters.display.Display`.

    Shows every frame the Display sees as a scaled pixmap inside the
    node body. Frames arrive on the worker thread via the node's
    ``frame_callback``; a queued :class:`Signal` hops them to the UI
    thread where the pixmap is swapped in.
    """

    #: Worker thread emits a ready QImage; connected via
    #: AutoConnection, which resolves to a queued connection across
    #: threads so Qt handles the marshalling for us.
    _frame_ready = Signal(QImage)

    _PREVIEW_MIN_W: int = 180
    _PREVIEW_MIN_H: int = 100

    def __init__(self, node: Display) -> None:
        super().__init__(node)
        self._label = QLabel()
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setMinimumSize(self._PREVIEW_MIN_W, self._PREVIEW_MIN_H)
        self._label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        # Dark backdrop so empty/letterboxed space reads as "no frame".
        self._label.setStyleSheet(
            "QLabel { background: #111; border: 1px solid #333; }"
        )
        self._placeholder_text = "(no frame yet)"
        self._label.setText(self._placeholder_text)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(self._label)

        self._frame_ready.connect(self._on_frame_ready)
        node.set_frame_callback(self._emit_from_worker)

    # ── Worker thread ──────────────────────────────────────────────────────────

    def _emit_from_worker(self, frame: np.ndarray) -> None:
        """Called from whichever thread runs the Display node's process.

        Convert to a self-owning QImage (so the underlying numpy buffer
        can be freed / rewritten without tearing the pixmap) and hand
        off across threads via the queued signal.
        """
        try:
            qimg = _numpy_to_qimage(frame)
        except Exception:
            logger.exception("DisplayPreview: failed to convert frame to QImage")
            return
        self._frame_ready.emit(qimg)

    # ── UI thread ──────────────────────────────────────────────────────────────

    @Slot(QImage)
    def _on_frame_ready(self, qimg: QImage) -> None:
        pixmap = QPixmap.fromImage(qimg).scaled(
            self._label.width(),
            self._label.height(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._label.setPixmap(pixmap)


# ── numpy → QImage ─────────────────────────────────────────────────────────────


def _numpy_to_qimage(frame: np.ndarray) -> QImage:
    """Wrap a uint8 numpy frame as a self-owning :class:`QImage`.

    Supports single-channel greyscale and 3-channel BGR (cv2
    convention). The returned QImage is ``.copy()``-ed so it owns its
    pixel data independently of the numpy array — safe to hand across
    threads or to keep after the source buffer is rewritten.
    """
    if frame.dtype != np.uint8:
        frame = frame.astype(np.uint8, copy=False)
    if not frame.flags["C_CONTIGUOUS"]:
        frame = np.ascontiguousarray(frame)

    if frame.ndim == 2:
        h, w = frame.shape
        fmt = QImage.Format.Format_Grayscale8
        qimg = QImage(frame.data, w, h, w, fmt)
    elif frame.ndim == 3 and frame.shape[2] == 3:
        h, w, _ = frame.shape
        # cv2 stores BGR; QImage has a native BGR888 format so no
        # per-pixel swap is needed.
        qimg = QImage(frame.data, w, h, 3 * w, QImage.Format.Format_BGR888)
    elif frame.ndim == 3 and frame.shape[2] == 4:
        h, w, _ = frame.shape
        qimg = QImage(frame.data, w, h, 4 * w, QImage.Format.Format_BGRA8888)
    else:
        raise ValueError(f"Unsupported frame shape for preview: {frame.shape}")

    return qimg.copy()


# ── Registry ───────────────────────────────────────────────────────────────────

_PREVIEW_WIDGET_CLASSES: dict[type[NodeBase], type[_PreviewWidgetBase]] = {
    Display: DisplayPreview,
}


def build_preview_widget(node: NodeBase) -> _PreviewWidgetBase | None:
    """Return an inline preview for *node*, or ``None`` if the node
    doesn't have one registered.

    :class:`~ui.node_item.NodeItem` calls this after building the
    param widgets; a non-``None`` result is embedded in the node body
    below the params.
    """
    cls = _PREVIEW_WIDGET_CLASSES.get(type(node))
    if cls is None:
        return None
    try:
        return cls(node)
    except Exception:
        logger.exception(
            "Failed to build %s preview widget for %s",
            cls.__name__, type(node).__name__,
        )
        return None

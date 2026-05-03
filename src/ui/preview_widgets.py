from __future__ import annotations

import logging

import cv2
import numpy as np
from typing_extensions import override

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core import notifications
from core.io_data import IoData, IoDataType
from core.node_base import NodeBase
from nodes.debug.meta_inspector import MetaInspector, format_meta
from nodes.debug.play_gate import PlayGate
from nodes.filters.display import Display, format_matrix, format_scalar

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

    Two modes, switched by the node's "show metadata" header toggle:

    - **Image mode (default).** Every frame the Display sees is
      rendered as a scaled pixmap (or formatted text for SCALAR /
      MATRIX payloads), with a status line beneath listing FPS,
      running frame number, and payload shape.
    - **Meta mode.** A scrollable text dump of the IoMeta + payload
      summary — the same rendering the standalone
      :class:`MetaInspector` provides.

    Both pages stay in sync with each frame so toggling the header
    swap is instant. Frames arrive on the worker thread via the
    node's ``frame_callback``; queued :class:`Signal`-s hop them to
    the UI thread before any QLabel updates.
    """

    #: Worker thread emits a ready QImage and the status string for
    #: image payloads. AutoConnection resolves to a queued connection
    #: across threads so Qt handles the marshalling for us.
    _frame_ready = Signal(QImage, str)
    #: Worker thread emits formatted text and the status string for
    #: SCALAR / MATRIX payloads.
    _text_ready = Signal(str, str)
    #: Worker thread emits the formatted meta dump for the meta page.
    _meta_ready = Signal(str)
    #: UI thread emits when the node's ``show_meta`` flag flips so
    #: the stacked widget can swap pages without polling.
    _mode_changed = Signal()

    _PREVIEW_MIN_W: int = 180
    _PREVIEW_MIN_H: int = 100

    _STATUS_PLACEHOLDER: str = "—"
    _META_PLACEHOLDER: str = "(run the flow to see meta)"

    def __init__(self, node: Display) -> None:
        super().__init__(node)
        # ── Image page ──────────────────────────────────────────────
        self._label = QLabel()
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setMinimumSize(self._PREVIEW_MIN_W, self._PREVIEW_MIN_H)
        # Expanding on both axes so the NodeItem's resize grip can grow
        # the preview to fill the user-chosen body area.
        self._label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._label.setStyleSheet(
            "QLabel { background: #111; border: 1px solid #333;"
            "         color: #f0c83c; font-family: 'Consolas','Menlo',monospace; }"
        )
        self._placeholder_text = "(no frame yet)"
        self._label.setText(self._placeholder_text)

        # Status bar beneath the image. Fixed height so the image area
        # owns all the slack from the resize grip.
        self._status = QLabel(self._STATUS_PLACEHOLDER)
        self._status.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
        )
        self._status.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed,
        )
        self._status.setStyleSheet(
            "QLabel { background: #1a1a1a; border: 1px solid #333;"
            "         border-top: none; color: #d6d6d6;"
            "         font-family: 'Consolas','Menlo',monospace;"
            "         font-size: 11px; padding: 2px 6px; }"
        )

        self._image_page = QWidget()
        image_layout = QVBoxLayout(self._image_page)
        image_layout.setContentsMargins(0, 0, 0, 0)
        image_layout.setSpacing(0)
        image_layout.addWidget(self._label, 1)
        image_layout.addWidget(self._status, 0)

        # ── Meta page ───────────────────────────────────────────────
        self._meta_label = QLabel()
        self._meta_label.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
        )
        self._meta_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding,
        )
        self._meta_label.setStyleSheet(
            "QLabel { background: #111; color: #d6d6d6; padding: 4px;"
            "         font-family: 'Consolas','Menlo',monospace;"
            "         font-size: 11px; }"
        )
        # Word-wrap so a long source_path doesn't blow out the body
        # width and force the user to resize the node.
        self._meta_label.setWordWrap(True)
        self._meta_label.setText(self._META_PLACEHOLDER)

        self._meta_scroll = QScrollArea()
        self._meta_scroll.setWidget(self._meta_label)
        self._meta_scroll.setWidgetResizable(True)
        self._meta_scroll.setFrameShape(QFrame.Shape.Box)
        self._meta_scroll.setMinimumSize(self._PREVIEW_MIN_W, self._PREVIEW_MIN_H)
        self._meta_scroll.setStyleSheet(
            "QScrollArea { background: #111; border: 1px solid #333; }"
        )

        # ── Stack ───────────────────────────────────────────────────
        self._stack = QStackedWidget()
        self._stack.addWidget(self._image_page)
        self._stack.addWidget(self._meta_scroll)

        # Mirror Expanding on the enclosing widget so its parent layout
        # honours vertical stretch rather than collapsing to sizeHint.
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._stack)

        # Original-resolution frame; we always scale from this to avoid
        # losing quality on successive resizes.
        self._source_image: QImage | None = None

        self._frame_ready.connect(self._on_frame_ready)
        self._text_ready.connect(self._on_text_ready)
        self._meta_ready.connect(self._on_meta_ready)
        self._mode_changed.connect(self._on_mode_changed)
        node.set_frame_callback(self._emit_from_worker)
        node.set_show_meta_callback(self._mode_changed.emit)
        # Show whichever page matches the node's current flag (defaults
        # to image, but a flow loaded with the toggle on would land
        # straight on meta).
        self._on_mode_changed()

    @override
    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._render_scaled()

    # ── Worker thread ──────────────────────────────────────────────────────────

    def _emit_from_worker(self, in_data: IoData) -> None:
        """Called from whichever thread runs the Display node's process.

        Updates both pages of the stack so the toggle is instant. The
        meta-text emit is unconditional; image-mode dispatches on
        payload kind: image payloads convert to a self-owning QImage
        (so the underlying numpy buffer can be freed without tearing
        the pixmap) and hop across threads via ``_frame_ready``;
        SCALAR / MATRIX payloads format to a string and hop via
        ``_text_ready``. The current FPS and frame count are read
        from the node here, on the worker thread, so the snapshot
        stays consistent with the payload being sent.
        """
        node = self._node
        assert isinstance(node, Display)
        status = _format_status(
            node.current_fps, node.frames_processed, in_data.payload,
        )

        # Keep the meta page in lockstep with the image page so
        # toggling the header switches instantly to the right text.
        self._meta_ready.emit(format_meta(in_data))

        if in_data.type is IoDataType.SCALAR:
            self._text_ready.emit(format_scalar(in_data.payload), status)
            return
        if in_data.type is IoDataType.MATRIX:
            self._text_ready.emit(format_matrix(in_data.payload), status)
            return

        try:
            qimg = numpy_to_qimage(in_data.payload)
        except Exception as exc:
            # Don't crash the run on a single bad frame; surface the
            # failure as a non-blocking warning so the user notices
            # (used to silently log-and-drop, which hid issue #179
            # for both PNG and WebP).
            logger.exception("DisplayPreview: failed to convert frame to QImage")
            notifications.warn(
                f"Display preview: could not render frame "
                f"(shape={getattr(in_data.payload, 'shape', '?')}): {exc}"
            )
            return
        self._frame_ready.emit(qimg, status)

    # ── UI thread ──────────────────────────────────────────────────────────────

    @Slot(QImage, str)
    def _on_frame_ready(self, qimg: QImage, status: str) -> None:
        self._source_image = qimg
        self._render_scaled()
        self._status.setText(status)

    @Slot(str, str)
    def _on_text_ready(self, text: str, status: str) -> None:
        # Switching to text mode invalidates any cached image so a
        # later resize doesn't redraw stale pixels behind the text.
        self._source_image = None
        self._label.setPixmap(QPixmap())
        self._label.setText(text)
        self._status.setText(status)

    @Slot(str)
    def _on_meta_ready(self, text: str) -> None:
        self._meta_label.setText(text)
        # Same belt-and-braces nudge as the standalone MetaInspector
        # widget — same-thread emits during click handlers can leave
        # the proxy widget without a fresh paint until the next
        # event-loop turn.
        self._meta_label.update()

    @Slot()
    def _on_mode_changed(self) -> None:
        node = self._node
        assert isinstance(node, Display)
        target = self._meta_scroll if node.show_meta else self._image_page
        self._stack.setCurrentWidget(target)

    def _render_scaled(self) -> None:
        if self._source_image is None:
            return
        pixmap = QPixmap.fromImage(self._source_image).scaled(
            self._label.width(),
            self._label.height(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._label.setPixmap(pixmap)


# ── Status line ───────────────────────────────────────────────────────────────


def _format_status(
    fps: float | None, frame_count: int, payload: np.ndarray,
) -> str:
    """Format the status line shown beneath the preview image.

    Reports FPS, the running frame number, and the resolution /
    shape of the current payload. FPS is omitted (rendered as a dash)
    on the very first frame, before a measurable interval exists.
    Image shapes render as ``W×H``; matrices keep their numpy shape;
    scalars show ``scalar``.
    """
    fps_text = f"{fps:.1f}" if fps is not None else "—"

    if payload.ndim == 0:
        size_text = "scalar"
    elif payload.ndim == 2:
        h, w = payload.shape
        size_text = f"{w}×{h}"
    elif payload.ndim == 3:
        h, w = payload.shape[:2]
        size_text = f"{w}×{h}"
    else:
        size_text = "×".join(str(d) for d in payload.shape)

    return f"FPS {fps_text}   N {frame_count}   {size_text}"


# ── numpy → QImage ─────────────────────────────────────────────────────────────


def numpy_to_qimage(frame: np.ndarray) -> QImage:
    """Wrap a uint8 numpy frame as a self-owning :class:`QImage`.

    Supports single-channel greyscale, 3-channel BGR, and 4-channel
    BGRA (cv2 convention). The returned QImage is ``.copy()``-ed so it
    owns its pixel data independently of the numpy array — safe to
    hand across threads or to keep after the source buffer is rewritten.
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
        # PySide6 has no Format_BGRA8888 enum (only Format_RGBA8888),
        # so the channel order has to flip before construction. The
        # cvtColor copy is unavoidable — passing BGRA bytes through
        # an RGBA-tagged QImage swaps the red and blue channels.
        # Issue: #179
        rgba = np.ascontiguousarray(cv2.cvtColor(frame, cv2.COLOR_BGRA2RGBA))
        h, w, _ = rgba.shape
        qimg = QImage(rgba.data, w, h, 4 * w, QImage.Format.Format_RGBA8888)
    else:
        raise ValueError(f"Unsupported frame shape for preview: {frame.shape}")

    return qimg.copy()


# ── MetaInspector preview ─────────────────────────────────────────────────────


class MetaInspectorPreview(_PreviewWidgetBase):
    """Inline preview for :class:`~nodes.debug.meta_inspector.MetaInspector`.

    Shows the :class:`~core.io_data.IoMeta` of every frame that passes
    through the inspector, plus the payload kind and shape. The text
    arrives on the worker thread via the node's frame_callback; a
    queued :class:`Signal` hops it to the UI thread before the label
    is updated.
    """

    _text_ready = Signal(str)

    _PREVIEW_MIN_W: int = 220
    _PREVIEW_MIN_H: int = 90

    def __init__(self, node: MetaInspector) -> None:
        super().__init__(node)
        self._label = QLabel()
        self._label.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        self._label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding,
        )
        self._label.setStyleSheet(
            "QLabel { background: #111; color: #d6d6d6; padding: 4px;"
            "         font-family: 'Consolas','Menlo',monospace;"
            "         font-size: 11px; }"
        )
        # Word-wrap so a long source_path doesn't blow out the body
        # width and force the user to resize the node.
        self._label.setWordWrap(True)
        self._label.setText("(run the flow to see meta)")

        # Wrap the label in a QScrollArea so meta blocks taller than
        # the preview box scroll instead of forcing the node to grow.
        # ``setWidgetResizable`` lets the inner label expand to the
        # viewport width (so word-wrap kicks in at the visible width)
        # while the vertical scrollbar appears on overflow.
        self._scroll = QScrollArea()
        self._scroll.setWidget(self._label)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.Box)
        self._scroll.setMinimumSize(self._PREVIEW_MIN_W, self._PREVIEW_MIN_H)
        self._scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding,
        )
        self._scroll.setStyleSheet(
            "QScrollArea { background: #111; border: 1px solid #333; }"
        )

        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding,
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._scroll)

        # Auto-connection delivers cross-thread emits via a queued
        # connection. Same-thread emits (e.g. when ``request_emit``
        # on a PlayGate fires the callback chain on the UI thread)
        # become direct calls — already handled.
        self._text_ready.connect(self._on_text_ready)
        node.set_frame_callback(self._emit_from_worker)

    def _emit_from_worker(self, data: IoData) -> None:
        self._text_ready.emit(format_meta(data))

    @Slot(str)
    def _on_text_ready(self, text: str) -> None:
        self._label.setText(text)
        # Belt-and-braces repaint nudge: setText already calls
        # ``update`` internally, but a same-thread emit during a
        # click handler can leave the proxy widget without a fresh
        # paint event until the next event-loop turn. Forcing
        # ``update`` is cheap and removes any timing ambiguity.
        self._label.update()


# ── PlayGate preview ──────────────────────────────────────────────────────────


class PlayGatePreview(_PreviewWidgetBase):
    """Inline preview for :class:`~nodes.debug.play_gate.PlayGate`.

    Hosts a Play button inside the node body. The button is enabled
    when the gate has a queued frame and disabled otherwise; clicking
    it asks the gate to release the queued frame downstream. The
    queue-state hop crosses threads via a queued :class:`Signal`.
    """

    _state_changed = Signal(bool)

    _PREVIEW_MIN_W: int = 140
    _PREVIEW_MIN_H: int = 56

    def __init__(self, node: PlayGate) -> None:
        super().__init__(node)
        self._button = QPushButton("▶  Play")
        self._button.setEnabled(False)
        self._button.setMinimumSize(self._PREVIEW_MIN_W, self._PREVIEW_MIN_H)
        self._button.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding,
        )
        self._button.setStyleSheet(
            "QPushButton { background: #2b6cb0; color: white;"
            "              border: 1px solid #1a4577;"
            "              padding: 6px 10px; font-weight: bold; }"
            "QPushButton:disabled { background: #333; color: #777; }"
            "QPushButton:hover:enabled { background: #3478c2; }"
        )
        self._button.clicked.connect(self._on_clicked)

        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding,
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._button)

        self._state_changed.connect(self._on_state_changed)
        node.set_state_callback(self._emit_from_worker)

    def _emit_from_worker(self, queued: bool) -> None:
        self._state_changed.emit(queued)

    @Slot(bool)
    def _on_state_changed(self, queued: bool) -> None:
        self._button.setEnabled(queued)

    @Slot()
    def _on_clicked(self) -> None:
        # Don't pre-disable: with the FIFO queue, a click only drains
        # one frame, and the gate fires its state callback only on
        # the empty <-> non-empty transition. Defensively disabling
        # here would strand the user with a still-non-empty queue
        # and a permanently dim button. A fast double-click is fine
        # — each click pops one frame, that's the desired step
        # behaviour.
        node = self._node
        assert isinstance(node, PlayGate)
        node.request_emit()


# ── Registry ───────────────────────────────────────────────────────────────────

_PREVIEW_WIDGET_CLASSES: dict[type[NodeBase], type[_PreviewWidgetBase]] = {
    Display: DisplayPreview,
    MetaInspector: MetaInspectorPreview,
    PlayGate: PlayGatePreview,
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

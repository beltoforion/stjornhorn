from __future__ import annotations

import time
from typing import Callable

import cv2
import numpy as np
from typing_extensions import override

from core.io_data import IMAGE_TYPES, IoData, IoDataType
from core.node_base import NodeBase
from core.port import InputPort, OutputPort


_DISPLAY_TYPES = frozenset(IMAGE_TYPES | {IoDataType.SCALAR, IoDataType.MATRIX})


class Display(NodeBase):
    """Pass-through node that surfaces each frame to an inline preview.

    Stores the most recent payload on :attr:`latest_frame` and, when the
    UI attaches one via :meth:`set_frame_callback`, invokes the
    callback with every new :class:`IoData`. The payload is forwarded on
    the output unchanged so the node can sit inline between any two
    others (e.g. upstream of a VideoSink to watch encoding as it
    happens).

    Accepts every payload kind: image (colour or greyscale), SCALAR and
    MATRIX. The preview widget on the UI side decides how to render
    each kind (pixmap for images, formatted text for scalars and
    matrices).

    A small debug overlay (FPS + frame count) is rendered into the
    top-left of each *displayed* image frame. The frame count is shown
    from the very first tick; the FPS line is added from the second tick
    once a measurable ``dt`` is available. The overlay is preview-only —
    the output port still forwards the original :class:`IoData` so a
    downstream VideoSink isn't recording debug overlays into the file.

    The node itself is Qt-free — the preview widget lives on the UI
    side in :mod:`ui.preview_widgets`; the worker-thread → main-thread
    hand-off is the UI widget's responsibility (queued signal).
    """

    # Exponential-moving-average smoothing factor for the FPS readout.
    # 0.2 gives a half-life of ~3 frames — fast enough to track a real
    # speed-up, slow enough to absorb single-frame jitter from cv2 ops.
    _FPS_EMA_ALPHA: float = 0.2

    def __init__(self) -> None:
        super().__init__("Display", section="Output")
        self._latest_frame:    np.ndarray | None = None
        self._frame_callback:  Callable[[IoData], None] | None = None
        self._last_frame_ts:   float | None = None
        self._fps_ema:         float | None = None
        self._frame_count:     int = 0

        self._add_input(InputPort("image", set(_DISPLAY_TYPES)))
        self._add_output(OutputPort("image", set(_DISPLAY_TYPES)))

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def latest_frame(self) -> np.ndarray | None:
        """Most recent payload seen, or ``None`` before any run.

        For image payloads this is the overlay-annotated frame (so the
        preview widget renders the debug info); for SCALAR / MATRIX
        payloads it is the raw 0-d / 2-d array unchanged. The output
        port always forwards the original payload either way.
        """
        return self._latest_frame

    @property
    def frames_processed(self) -> int:
        """Total frames dispatched since the last run started."""
        return self._frame_count

    # ── UI integration ─────────────────────────────────────────────────────────

    def set_frame_callback(
        self, callback: Callable[[IoData], None] | None,
    ) -> None:
        """Attach (or clear) a callback invoked with each new IoData.

        Receives the full :class:`IoData` envelope (not just the array)
        so the preview widget can dispatch on payload kind — image
        pixmap vs. scalar/matrix text.

        The callback fires on whichever thread :meth:`process_impl`
        runs on — the UI widget is responsible for marshalling back
        to the main thread, typically via a queued Qt signal.
        """
        self._frame_callback = callback

    # ── NodeBase interface ─────────────────────────────────────────────────────

    @override
    def _before_run_impl(self) -> None:
        super()._before_run_impl()
        self._latest_frame  = None
        self._last_frame_ts = None
        self._fps_ema       = None
        self._frame_count   = 0

    @override
    def process_impl(self) -> None:
        in_data = self.inputs[0].data

        self._frame_count += 1

        # Track dispatch cadence regardless of payload kind — a SCALAR
        # stream has the same notion of "frames per second" as an
        # image stream, even if we don't render an overlay onto it.
        now = time.monotonic()
        if self._last_frame_ts is not None:
            dt = now - self._last_frame_ts
            if dt > 0.0:
                inst_fps = 1.0 / dt
                if self._fps_ema is None:
                    self._fps_ema = inst_fps
                else:
                    self._fps_ema = (
                        self._FPS_EMA_ALPHA * inst_fps
                        + (1.0 - self._FPS_EMA_ALPHA) * self._fps_ema
                    )
        self._last_frame_ts = now

        # Image payloads get the debug overlay drawn on a copy for the
        # preview; SCALAR / MATRIX payloads bypass the overlay since
        # the text-mode preview has no image to annotate. The view
        # IoData (annotated copy or original) is what the callback
        # receives — the output port always forwards the original.
        if in_data.is_image():
            annotated = self._draw_overlay(in_data.payload, self._fps_ema, self._frame_count)
            view_data = IoData(in_data.type, payload=annotated)
            self._latest_frame = annotated
        else:
            view_data = in_data
            self._latest_frame = in_data.payload

        if self._frame_callback is not None:
            self._frame_callback(view_data)

        # Forward the original payload — overlays are display-only so a
        # downstream sink (e.g. VideoSink) doesn't record them to disk.
        self.outputs[0].send(in_data)

    # ── Overlay ────────────────────────────────────────────────────────────────

    @staticmethod
    def _draw_overlay(
        image: np.ndarray,
        fps: float | None,
        frame_count: int,
    ) -> np.ndarray:
        """Return a copy of *image* with a debug overlay in the top-left.

        Shows the frame count on every tick. The FPS line is added from
        tick 2 onwards once a measurable ``dt`` is available.
        Greyscale (2-D) and colour (3-D) images are both handled.
        """
        annotated = image.copy()
        font  = cv2.FONT_HERSHEY_SIMPLEX
        scale = 0.6
        thick = 1
        pad   = 4

        lines: list[str] = []
        if fps is not None:
            lines.append(f"FPS {fps:5.1f}")
        lines.append(f"N   {frame_count:5d}")

        sizes = [cv2.getTextSize(t, font, scale, thick) for t in lines]
        line_h   = sizes[0][0][1]
        baseline = sizes[0][1]
        total_w  = max(s[0][0] for s in sizes)
        line_gap = 6  # px between successive baselines

        x     = 8
        y_top = 8 + line_h  # baseline of the first rendered line

        rect_top    = y_top - line_h - pad
        rect_bottom = y_top + (len(lines) - 1) * (line_h + line_gap) + baseline + pad
        rect_right  = x + total_w + pad

        # Greyscale (2-D) and colour (3-D) take different scalar shapes for
        # cv2.rectangle / putText — branch once instead of guessing.
        is_grey = annotated.ndim == 2
        bg = 0         if is_grey else (0, 0, 0)
        fg = 255       if is_grey else (255, 255, 255)

        cv2.rectangle(
            annotated,
            (x - pad, rect_top),
            (rect_right, rect_bottom),
            bg, -1,
        )

        for i, text in enumerate(lines):
            y = y_top + i * (line_h + line_gap)
            cv2.putText(annotated, text, (x, y), font, scale, fg, thick, cv2.LINE_AA)

        return annotated

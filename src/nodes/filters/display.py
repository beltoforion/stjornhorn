from __future__ import annotations

import time
from typing import Callable

import cv2
import numpy as np
from typing_extensions import override

from core.io_data import IMAGE_TYPES
from core.node_base import NodeBase, NodeParam
from core.port import InputPort, OutputPort


class Display(NodeBase):
    """Pass-through node that surfaces each frame to an inline preview.

    Stores the most recent frame on :attr:`latest_frame` and, when the
    UI attaches one via :meth:`set_frame_callback`, invokes the
    callback with every new frame. The ``IoData`` is forwarded on the
    output unchanged so the node can sit inline between any two others
    (e.g. upstream of a VideoSink to watch encoding as it happens).

    A small FPS read-out is always rendered into the top-left of the
    *displayed* frame from the second tick onwards (the first tick has
    no measurable ``dt`` to derive a rate from). The overlay is
    preview-only — the output port still forwards the original
    :class:`IoData` so a downstream VideoSink isn't recording debug
    overlays into the file.

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
        self._frame_callback:  Callable[[np.ndarray], None] | None = None
        self._last_frame_ts:   float | None = None
        self._fps_ema:         float | None = None

        self._add_input(InputPort("image", set(IMAGE_TYPES)))
        self._add_output(OutputPort("image", set(IMAGE_TYPES)))

    # ── Parameters ─────────────────────────────────────────────────────────────

    @property
    @override
    def params(self) -> list[NodeParam]:
        return []

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def latest_frame(self) -> np.ndarray | None:
        """Most recent frame seen, or ``None`` before any run.

        From the second tick of a run onwards this is the FPS-annotated
        frame (so the preview widget renders the overlay); the output
        port always forwards the original payload.
        """
        return self._latest_frame

    # ── UI integration ─────────────────────────────────────────────────────────

    def set_frame_callback(
        self, callback: Callable[[np.ndarray], None] | None,
    ) -> None:
        """Attach (or clear) a callback invoked with each new frame.

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

    @override
    def process_impl(self) -> None:
        in_data = self.inputs[0].data
        image: np.ndarray = in_data.image

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

        displayed = image
        if self._fps_ema is not None:
            displayed = self._draw_fps_overlay(image, self._fps_ema)

        self._latest_frame = displayed
        if self._frame_callback is not None:
            self._frame_callback(displayed)

        # Forward the original payload — overlays are display-only so a
        # downstream sink (e.g. VideoSink) doesn't record them to disk.
        self.outputs[0].send(in_data)

    # ── Overlay ────────────────────────────────────────────────────────────────

    @staticmethod
    def _draw_fps_overlay(image: np.ndarray, fps: float) -> np.ndarray:
        """Return a copy of *image* with a small FPS read-out in the top-left."""
        annotated = image.copy()
        text   = f"FPS {fps:5.1f}"
        font   = cv2.FONT_HERSHEY_SIMPLEX
        scale  = 0.6
        thick  = 1
        (tw, th), baseline = cv2.getTextSize(text, font, scale, thick)
        x, y = 8, 8 + th
        pad  = 4

        # Greyscale (2-D) and colour (3-D) take different scalar shapes for
        # cv2.rectangle / putText — branch once instead of guessing.
        if annotated.ndim == 2:
            cv2.rectangle(
                annotated,
                (x - pad, y - th - pad),
                (x + tw + pad, y + baseline),
                0, -1,
            )
            cv2.putText(annotated, text, (x, y), font, scale, 255, thick, cv2.LINE_AA)
        else:
            cv2.rectangle(
                annotated,
                (x - pad, y - th - pad),
                (x + tw + pad, y + baseline),
                (0, 0, 0), -1,
            )
            cv2.putText(
                annotated, text, (x, y), font, scale,
                (255, 255, 255), thick, cv2.LINE_AA,
            )
        return annotated

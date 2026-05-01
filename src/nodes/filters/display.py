from __future__ import annotations

import time
from typing import Callable

import numpy as np
from typing_extensions import override

from core.io_data import IMAGE_TYPES, IoData, IoDataType
from core.node_base import NodeBase
from core.port import InputPort, OutputPort


_DISPLAY_TYPES = frozenset(IMAGE_TYPES | {IoDataType.SCALAR, IoDataType.MATRIX})


class Display(NodeBase):
    """Pass-through node that surfaces each frame to an inline preview.

    The payload is forwarded on the output unchanged so the node can
    sit inline between any two others (e.g. upstream of a VideoSink
    to watch encoding as it happens). Accepts image (colour or
    greyscale), SCALAR and MATRIX payloads.

    FPS and frame count are tracked on the node and exposed as
    properties; the inline preview widget reads them to render a
    status line beneath the image. The pixel payload is never
    annotated, so downstream sinks see clean frames.
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

        Always the original payload — the node no longer mutates the
        pixels, so what the preview renders matches what the output
        port forwards.
        """
        return self._latest_frame

    @property
    def frames_processed(self) -> int:
        """Total frames dispatched since the last run started."""
        return self._frame_count

    @property
    def current_fps(self) -> float | None:
        """Smoothed frames-per-second for the dispatch cadence.

        ``None`` until at least two frames have been seen — a single
        tick has no measurable interval.
        """
        return self._fps_ema

    # ── UI integration ─────────────────────────────────────────────────────────

    def set_frame_callback(
        self, callback: Callable[[IoData], None] | None,
    ) -> None:
        """Attach (or clear) a callback invoked with each new IoData.

        Receives the full :class:`IoData` envelope (not just the array)
        so the preview widget can dispatch on payload kind — image
        pixmap vs. scalar/matrix text. The widget can read
        :attr:`current_fps` and :attr:`frames_processed` from the node
        at callback time to render the status line.

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
        # image stream.
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

        self._latest_frame = in_data.payload

        if self._frame_callback is not None:
            self._frame_callback(in_data)

        self.outputs[0].send(in_data)

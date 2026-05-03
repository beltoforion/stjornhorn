from __future__ import annotations

import time
from typing import Callable

import numpy as np
from typing_extensions import override

from core.io_data import IMAGE_TYPES, IoData, IoDataType
from core.node_base import Command, NodeBase, Toggle
from core.port import InputPort, OutputPort
from nodes.debug.meta_inspector import format_meta


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

    HEADER_ICON = "visibility"

    def __init__(self) -> None:
        super().__init__("Display", section="Output")
        self._latest_frame:    np.ndarray | None = None
        self._last_data:       IoData | None = None
        self._frame_callback:  Callable[[IoData], None] | None = None
        self._last_frame_ts:   float | None = None
        self._fps_ema:         float | None = None
        self._frame_count:     int = 0
        # Header toggle: when on, the preview swaps the image / status
        # bar for a scrollable meta-text view (the same rendering as
        # the standalone MetaInspector). The widget polls
        # :attr:`show_meta` on each repaint and re-subscribes to mode
        # flips via :meth:`set_show_meta_callback`.
        self._show_meta:                bool = False
        self._show_meta_callback:       Callable[[], None] | None = None

        self._add_input(InputPort("image", set(_DISPLAY_TYPES)))
        self._add_output(OutputPort("image", set(_DISPLAY_TYPES)))

        self._header_items.append(Toggle(
            glyph="info",
            tooltip="Show frame metadata instead of image",
            handler=self._toggle_show_meta,
            is_active=lambda: self._show_meta,
        ))
        self._header_items.append(Command(
            glyph="content_copy",
            tooltip="Copy what's shown in the preview to the clipboard",
            handler=self._copy_visible,
        ))

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

    @property
    def show_meta(self) -> bool:
        """True when the preview should render frame metadata instead
        of the image / status bar. Flipped by the header toggle; the
        widget polls this on each repaint."""
        return self._show_meta

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

    def set_show_meta_callback(
        self, callback: Callable[[], None] | None,
    ) -> None:
        """Attach (or clear) a callback fired when :attr:`show_meta`
        flips. The preview widget uses it to swap which page of its
        stack is visible without polling."""
        self._show_meta_callback = callback

    def _toggle_show_meta(self) -> None:
        """Header-toggle handler: flip ``show_meta`` and notify the
        widget so it can repaint in the new mode."""
        self._show_meta = not self._show_meta
        if self._show_meta_callback is not None:
            self._show_meta_callback()

    def _copy_visible(self) -> object:
        """Header-command handler: return whatever the preview is
        currently showing, in the form the editor's clipboard
        dispatcher expects.

        - Meta mode → the formatted meta text (str).
        - Image mode + IMAGE payload → the raw uint8 array (ndarray;
          the editor pushes it as an image).
        - Image mode + SCALAR / MATRIX payload → the rendered text
          (str), matching what's drawn in the preview label.
        - No frame seen yet → ``None`` (silent no-op).
        """
        data = self._last_data
        if data is None:
            return None
        if self._show_meta:
            return format_meta(data)
        if data.type is IoDataType.SCALAR:
            return format_scalar(data.payload)
        if data.type is IoDataType.MATRIX:
            return format_matrix(data.payload)
        # IMAGE: hand the array over; the editor turns it into a
        # QImage and writes ``setImage`` on the system clipboard.
        return data.payload

    # ── NodeBase interface ─────────────────────────────────────────────────────

    @override
    def _before_run_impl(self) -> None:
        super()._before_run_impl()
        self._latest_frame  = None
        self._last_data     = None
        self._last_frame_ts = None
        self._fps_ema       = None
        self._frame_count   = 0

    @override
    def process_impl(self) -> None:
        in_data = self.inputs[0].data
        self._last_data = in_data

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


def format_scalar(arr: np.ndarray) -> str:
    """Format a 0-d numpy array for the Display preview label and the
    "copy visible" command.

    Integers render without a decimal point; floats use up to 4
    decimals so a multiplier like 0.5 stays legible without trailing
    zero-noise.
    """
    value = arr.item()
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    return f"{float(value):.4g}"


def format_matrix(arr: np.ndarray) -> str:
    """Format a 2-D numpy array as a compact text grid for the
    preview label and the "copy visible" command.

    Caps the rendered shape so a large matrix doesn't blow out the
    preview label; truncated rows/cols are indicated with an ellipsis.
    """
    return np.array2string(arr, precision=3, suppress_small=True, threshold=64)

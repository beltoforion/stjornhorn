from __future__ import annotations

from typing import Callable

import numpy as np
from typing_extensions import override

from core.io_data import IMAGE_TYPES, IoData, IoDataType
from core.node_base import NodeBase, NodeParam
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

    The node itself is Qt-free — the preview widget lives on the UI
    side in :mod:`ui.preview_widgets`; the worker-thread → main-thread
    hand-off is the UI widget's responsibility (queued signal).
    """

    def __init__(self) -> None:
        super().__init__("Display", section="Output")
        self._latest_frame: np.ndarray | None = None
        self._frame_callback: Callable[[IoData], None] | None = None

        self._add_input(InputPort("image", set(_DISPLAY_TYPES)))
        self._add_output(OutputPort("image", set(_DISPLAY_TYPES)))

    # ── Parameters ─────────────────────────────────────────────────────────────

    @property
    @override
    def params(self) -> list[NodeParam]:
        return []

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def latest_frame(self) -> np.ndarray | None:
        """Most recent payload seen, or ``None`` before any run."""
        return self._latest_frame

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
        self._latest_frame = None

    @override
    def process_impl(self) -> None:
        in_data = self.inputs[0].data
        self._latest_frame = in_data.payload
        if self._frame_callback is not None:
            self._frame_callback(in_data)
        self.outputs[0].send(in_data)

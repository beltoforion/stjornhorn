from __future__ import annotations

import logging

import cv2
import numpy as np
from typing_extensions import override

from core.io_data import IMAGE_TYPES
from core.node_base import NodeBase, NodeParam, NodeParamType
from core.port import InputPort, OutputPort

logger = logging.getLogger(__name__)


class Display(NodeBase):
    """Pass-through node that shows each frame in a HighGUI window.

    Intended for live preview while the rest of the graph keeps
    running. Every frame is displayed as it arrives via
    :func:`cv2.imshow`, then emitted unchanged on the output so the
    node can sit inline between any two other nodes (e.g. upstream of
    a :class:`~nodes.sinks.video_sink.VideoSink` to watch encoding in
    real time).

    :func:`cv2.waitKey(1)` is called after each imshow so HighGUI
    actually pumps its event loop and paints — otherwise the window
    stays frozen on the first frame. The window is kept open after the
    flow finishes so the user can inspect the final image; it is
    destroyed at the start of the next run, or on an aborted run.

    Greyscale frames are shown directly (HighGUI handles both 2-D and
    3-channel arrays). The incoming ``IoData`` is forwarded as-is, so
    the output type tracks the input type.
    """

    def __init__(self) -> None:
        super().__init__("Display", section="Output")
        self._window_title: str = "Display"
        self._window_open: bool = False

        self._add_input(InputPort("image", set(IMAGE_TYPES)))
        self._add_output(OutputPort("image", set(IMAGE_TYPES)))

        self._apply_default_params()

    # ── Parameters ─────────────────────────────────────────────────────────────

    @property
    @override
    def params(self) -> list[NodeParam]:
        return [
            NodeParam("window_title", NodeParamType.STRING, {"default": "Display"}),
        ]

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def window_title(self) -> str:
        return self._window_title

    @window_title.setter
    def window_title(self, value: str) -> None:
        v = str(value).strip()
        if not v:
            raise ValueError("window_title must be a non-empty string")
        # Renaming an open window cleanly means tearing the old one down
        # first — cv2 can't rename in place and would otherwise orphan
        # the native window.
        if self._window_open and v != self._window_title:
            self._destroy_window()
        self._window_title = v

    # ── NodeBase interface ─────────────────────────────────────────────────────

    @override
    def _before_run_impl(self) -> None:
        super()._before_run_impl()
        # Start each run with a fresh window; if the previous run left
        # one up (the Display deliberately keeps it open so users can
        # inspect the last frame), close it now so state is clean.
        self._destroy_window()

    @override
    def process_impl(self) -> None:
        in_data = self.inputs[0].data
        image: np.ndarray = in_data.image

        if not self._window_open:
            cv2.namedWindow(self._window_title, cv2.WINDOW_AUTOSIZE)
            self._window_open = True

        cv2.imshow(self._window_title, image)
        # 1ms timeout lets HighGUI render the frame and process queued
        # OS events without blocking the pipeline.
        cv2.waitKey(1)

        self.outputs[0].send(in_data)

    @override
    def _after_run_impl(self, run_success: bool) -> None:
        super()._after_run_impl(run_success)
        # Leave the window up on success so users can look at the final
        # frame; tear it down on failure to avoid a stuck, stale window
        # from an aborted run.
        if not run_success:
            self._destroy_window()

    # ── Internals ──────────────────────────────────────────────────────────────

    def _destroy_window(self) -> None:
        if not self._window_open:
            return
        try:
            cv2.destroyWindow(self._window_title)
        except cv2.error:
            # The user may have already closed it via the OS chrome, or
            # the HighGUI backend may be refusing because the window is
            # already gone — either way, nothing useful to recover.
            logger.debug("cv2.destroyWindow(%r) raised; ignoring", self._window_title)
        self._window_open = False

from __future__ import annotations

import threading
from collections import deque
from typing import Callable

from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase
from core.port import InputPort, OutputPort


#: Every payload kind passes through; the gate is type-agnostic.
_ALL_TYPES: frozenset[IoDataType] = frozenset(IoDataType)


class PlayGate(NodeBase):
    """Pass-through node that buffers input frames until the user
    clicks Play.

    Behaviour:
      - Each incoming frame is appended to a FIFO queue; the preview
        widget's Play button becomes enabled as soon as anything is
        queued.
      - Each click releases **one** frame downstream — the oldest one
        in the queue, so the user steps through the stream in arrival
        order.
      - The queue is **unbounded**: a debug aid trades off memory for
        honesty (no silent drops). The user is expected to keep their
        feeder ranges reasonable; piping a long video stream straight
        into a Play Gate will cost real memory.

    The node is Qt-free; the preview widget owns the button and
    forwards clicks via :meth:`request_emit`. State changes (queue
    became non-empty / empty) are surfaced through
    :meth:`set_state_callback` so the widget can update its enabled
    state on the UI thread via a queued signal.
    """

    HEADER_ICON = "schedule"

    def __init__(self) -> None:
        super().__init__("Play Gate", section="Debug")
        self._add_input(InputPort("data", set(_ALL_TYPES)))
        self._add_output(OutputPort("data", set(_ALL_TYPES)))

        # The queue + finish-deferral state are touched from both the
        # worker thread (process_impl) and the UI thread
        # (request_emit), so a lock prevents lost-update races.
        self._lock = threading.Lock()
        self._queue: deque[IoData] = deque()
        # When the upstream finishes while frames are still queued,
        # the default _on_finish would close our outputs before the
        # user gets a chance to click through them — afterward,
        # send() raises "called after finish()" and the click
        # silently does nothing. Defer the output-side finish until
        # the queue drains; ``request_emit`` flushes the deferred
        # finish on the click that releases the last frame.
        self._pending_finish: bool = False
        self._state_callback: Callable[[bool], None] | None = None

    # ── UI integration ─────────────────────────────────────────────────────────

    def set_state_callback(
        self, callback: Callable[[bool], None] | None,
    ) -> None:
        """Attach a callback invoked when the queued state changes.

        The argument is ``True`` when a frame is queued (button should
        enable), ``False`` after a release or when the queue is empty.
        Fires on whichever thread caused the transition; the widget is
        responsible for marshalling back to the UI thread.
        """
        self._state_callback = callback

    def request_emit(self) -> None:
        """Release the next queued frame downstream, if any.

        Called from the UI thread when the Play button is clicked.
        Pops the oldest frame from the FIFO; no-op when the queue is
        empty (the button should be disabled in that case, but the
        no-op keeps a stale double-click safe). When the click drains
        the last queued frame and the upstream had already finished,
        the deferred finish is flushed so downstream sinks can wrap
        up.
        """
        with self._lock:
            if not self._queue:
                return
            data = self._queue.popleft()
            queue_now_empty = not self._queue
            flush_finish = queue_now_empty and self._pending_finish
            if flush_finish:
                self._pending_finish = False
        if queue_now_empty:
            self._notify_state(False)
        # send() is invoked OUTSIDE the lock so a downstream listener
        # that takes its own locks (or re-enters the gate via a fan-out
        # path) can't deadlock against us.
        self.outputs[0].send(data)
        if flush_finish:
            for port in self._outputs:
                port.finish()

    @property
    def queue_depth(self) -> int:
        """Number of frames currently buffered, waiting for Play."""
        with self._lock:
            return len(self._queue)

    @property
    def has_queued(self) -> bool:
        """True when at least one frame is waiting for a Play click."""
        with self._lock:
            return bool(self._queue)

    # ── NodeBase interface ─────────────────────────────────────────────────────

    @override
    def _before_run_impl(self) -> None:
        super()._before_run_impl()
        with self._lock:
            self._queue.clear()
            self._pending_finish = False
        self._notify_state(False)

    @override
    def process_impl(self) -> None:
        in_data = self.inputs[0].data
        with self._lock:
            self._queue.append(in_data)
            queue_just_filled = len(self._queue) == 1
        if queue_just_filled:
            self._notify_state(True)

    @override
    def _on_finish(self) -> None:
        """Defer output finish if frames are still queued.

        The default implementation would close the output ports as
        soon as upstream finishes — but that races with a slow user
        who hasn't clicked through every queued frame yet. Deferring
        lets ``request_emit`` step through the buffered frames before
        propagating the lifecycle signal.
        """
        with self._lock:
            still_queued = bool(self._queue)
            if still_queued:
                self._pending_finish = True
        if not still_queued:
            super()._on_finish()

    @override
    def _on_skipped_changed(self, skipped: bool) -> None:
        """When the user toggles the node into skip mode, flush every
        queued frame immediately and disable the button.

        Skip semantics on the rest of the framework are "this node is
        a wire" — incoming frames go straight to outputs via
        :meth:`_process_skipped`. Without this drain, the user would
        be left clicking through the pre-skip backlog while new
        frames already pass through automatically, which is exactly
        the inverse of what the toggle visually promises.
        """
        if not skipped:
            return
        with self._lock:
            backlog = list(self._queue)
            self._queue.clear()
            flush_finish = self._pending_finish
            if flush_finish:
                self._pending_finish = False
        if backlog:
            self._notify_state(False)
        for data in backlog:
            self.outputs[0].send(data)
        if flush_finish:
            for port in self._outputs:
                port.finish()

    # ── Internal ───────────────────────────────────────────────────────────────

    def _notify_state(self, queued: bool) -> None:
        cb = self._state_callback
        if cb is not None:
            cb(queued)

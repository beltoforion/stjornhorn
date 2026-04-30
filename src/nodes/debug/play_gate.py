from __future__ import annotations

import threading
from typing import Callable

from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase
from core.port import InputPort, OutputPort


#: Every payload kind passes through; the gate is type-agnostic.
_ALL_TYPES: frozenset[IoDataType] = frozenset(IoDataType)


class PlayGate(NodeBase):
    """Pass-through node that holds each input frame until the user
    clicks Play.

    Behaviour:
      - When a frame arrives at :attr:`process_impl`, it is queued and
        the preview widget's Play button becomes enabled.
      - When the user clicks Play, :meth:`request_emit` releases the
        queued frame downstream and disables the button until the
        next frame arrives.
      - Only the most recently received frame is held; if a second
        frame arrives before the user clicks, the first is dropped.
        This keeps the gate usable on fast streams (the user steps
        through whatever the stream surfaces at the moment of click)
        without an unbounded queue.

    The node is Qt-free; the preview widget owns the button and
    forwards clicks via :meth:`request_emit`. State changes (queue
    became non-empty / empty) are surfaced through
    :meth:`set_state_callback` so the widget can update its enabled
    state on the UI thread via a queued signal.
    """

    def __init__(self) -> None:
        super().__init__("Play Gate", section="Debug")
        self._add_input(InputPort("data", set(_ALL_TYPES)))
        self._add_output(OutputPort("data", set(_ALL_TYPES)))

        # The queue + click state is touched from both the worker
        # thread (process_impl) and the UI thread (request_emit), so a
        # lock prevents lost-update races on the single-slot cache.
        self._lock = threading.Lock()
        self._queued: IoData | None = None
        # When the upstream finishes while we still have a queued
        # frame, the default _on_finish would close our outputs
        # before the user gets a chance to click Play — afterward,
        # send() raises "called after finish()" and the click silently
        # does nothing. Defer the output-side finish until the queue
        # drains; ``request_emit`` flushes the deferred finish after
        # releasing the last frame.
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
        """Release the queued frame downstream, if any.

        Called from the UI thread when the Play button is clicked.
        No-op when nothing is queued (button should be disabled in
        that case, but the no-op keeps a stale double-click safe).
        """
        with self._lock:
            data = self._queued
            self._queued = None
            pending_finish = self._pending_finish
            self._pending_finish = False
        if data is None:
            return
        self._notify_state(False)
        # send() is invoked OUTSIDE the lock so a downstream listener
        # that takes its own locks (or re-enters the gate via a fan-out
        # path) can't deadlock against us.
        self.outputs[0].send(data)
        if pending_finish:
            for port in self._outputs:
                port.finish()

    @property
    def has_queued(self) -> bool:
        """True when a frame is currently waiting for a Play click."""
        with self._lock:
            return self._queued is not None

    # ── NodeBase interface ─────────────────────────────────────────────────────

    @override
    def _before_run_impl(self) -> None:
        super()._before_run_impl()
        with self._lock:
            self._queued = None
            self._pending_finish = False
        self._notify_state(False)

    @override
    def process_impl(self) -> None:
        in_data = self.inputs[0].data
        with self._lock:
            self._queued = in_data
        self._notify_state(True)

    @override
    def _on_finish(self) -> None:
        """Defer output finish if a frame is still queued.

        The default implementation would close the output ports as
        soon as upstream finishes — but that races with a slow user
        who hasn't clicked Play yet. Deferring lets ``request_emit``
        emit the last frame before propagating the lifecycle signal.
        """
        with self._lock:
            still_queued = self._queued is not None
            if still_queued:
                self._pending_finish = True
        if not still_queued:
            super()._on_finish()

    # ── Internal ───────────────────────────────────────────────────────────────

    def _notify_state(self, queued: bool) -> None:
        cb = self._state_callback
        if cb is not None:
            cb(queued)

from __future__ import annotations

import logging

import numpy as np
from typing_extensions import override

from core.io_data import IoDataType
from core.node_base import SinkNodeBase, NodeParam
from core.port import InputPort

logger = logging.getLogger(__name__)


class ValueSink(SinkNodeBase):
    """Sink node that consumes SCALAR / MATRIX payloads.

    Counterpart to :class:`~nodes.sources.value_source.ValueSource`.
    Lets a flow that produces numeric values (without ever rendering an
    image) terminate cleanly: the executor enforces the "every flow
    needs at least one sink" rule, and the existing image sinks
    (FileSink, VideoSink) only accept image payloads.

    The most recent received value is exposed via :attr:`latest_value`
    so debug code or future inspectors can read the final state.
    Every received value is also logged at DEBUG level so a verbose
    log captures the full stream.
    """

    def __init__(self) -> None:
        super().__init__("Value Sink", section="Sinks")
        self._latest_value: np.ndarray | None = None
        self._add_input(InputPort("value", {IoDataType.SCALAR, IoDataType.MATRIX}))

    # ── Parameters ─────────────────────────────────────────────────────────────

    @property
    @override
    def params(self) -> list[NodeParam]:
        return []

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def latest_value(self) -> np.ndarray | None:
        """Most recent payload seen, or ``None`` before any run."""
        return self._latest_value

    # ── NodeBase interface ─────────────────────────────────────────────────────

    @override
    def _before_run_impl(self) -> None:
        super()._before_run_impl()
        self._latest_value = None

    @override
    def process_impl(self) -> None:
        in_data = self.inputs[0].data
        self._latest_value = in_data.payload
        logger.debug("ValueSink received %s", in_data)

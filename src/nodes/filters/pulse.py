from __future__ import annotations

from typing_extensions import override

from core.io_data import IoDataType
from core.node_base import NodeBase
from core.port import InputPort, OutputPort


#: Every payload kind passes through; pulse is type-agnostic.
_ALL_TYPES: frozenset[IoDataType] = frozenset(IoDataType)


class Pulse(NodeBase):
    """Re-emit a held payload once per ``tick``.

    Pairs a one-shot upstream (an :class:`ImageSource`, a
    :class:`CsvSource`) with a streaming SCALAR clock so the held
    payload fires once per clock tick. Each emission carries
    ``meta["tick"] = <clock value>`` automatically — the framework's
    SCALAR-port auto-stamp (refactor M13) injects every SCALAR input
    on a node into outgoing meta under the port name, so a downstream
    sink template can reference ``$tick$`` without the sink needing
    a tick port of its own.

    Inputs:
      ``data``  — held payload, any type. Latched (``hold_last``) so
                  a one-shot source survives across tick fires.
      ``tick``  — SCALAR clock; each tick fires the node.

    Output:
      ``data``  — same payload, with ``meta["tick"]`` stamped.
    """

    def __init__(self) -> None:
        super().__init__("Pulse", section="Streaming")
        # ``data`` is held so one-shot sources don't go stale on
        # subsequent ticks. ``tick`` is the lifecycle driver — every
        # tick fires the node.
        self._add_input(InputPort("data", set(_ALL_TYPES), hold_last=True))
        self._add_input(InputPort("tick", {IoDataType.SCALAR}))
        self._add_output(OutputPort("data", set(_ALL_TYPES)))

    @override
    def process_impl(self) -> None:
        # Pure pass-through. ``meta["tick"]`` lands automatically via
        # OutputPort.send's SCALAR-port auto-stamp; no manual stamping
        # needed here.
        self.outputs[0].send(self.inputs[0].data)

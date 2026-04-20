from __future__ import annotations

import logging
import re

from core.node_base import NodeBase, SinkNodeBase, SourceNodeBase
from core.port import InputPort, OutputPort

logger = logging.getLogger(__name__)


DEFAULT_FLOW_NAME: str = "Untitled_flow"

# Allowed flow-name characters: ASCII letters, digits, underscore, hash,
# plus and minus. The set is intentionally narrow so that names are safe to
# use as filename stems on every platform without further escaping.
_DISALLOWED_NAME_CHARS = re.compile(r"[^a-zA-Z0-9_#+\-]")
_VALID_NAME_RE = re.compile(r"\A[a-zA-Z0-9_#+\-]+\Z")


def is_valid_flow_name(name: str) -> bool:
    """Return True iff ``name`` is non-empty and only uses allowed chars."""
    return _VALID_NAME_RE.match(name) is not None


def sanitize_flow_name(name: str) -> str:
    """Return ``name`` with disallowed characters stripped.

    Falls back to :data:`DEFAULT_FLOW_NAME` if the sanitized result is empty.
    Defensive helper: the UI should reject invalid names up-front, but code
    paths that construct :class:`Flow` directly still get a safe value.
    """
    cleaned = _DISALLOWED_NAME_CHARS.sub("", name)
    return cleaned or DEFAULT_FLOW_NAME


class Flow:
    """A directed acyclic graph of nodes connected by typed ports.

    Responsibilities:
      - Track which nodes belong to the flow.
      - Validate and create port-to-port connections.
      - Run the flow by starting all source nodes in registration order.
    """

    def __init__(self, name: str = DEFAULT_FLOW_NAME) -> None:
        self._name: str = sanitize_flow_name(name)
        self._nodes: list[NodeBase] = []

    # ── Identity ───────────────────────────────────────────────────────────────

    @property
    def name(self) -> str:
        """Human-readable flow name; always filesystem-safe."""
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        self._name = sanitize_flow_name(value)

    # ── Node management ────────────────────────────────────────────────────────

    def add_node(self, node: NodeBase) -> None:
        if node not in self._nodes:
            self._nodes.append(node)

    def remove_node(self, node: NodeBase) -> None:
        """Remove a node and disconnect all its ports."""
        for port in node.outputs:
            port.disconnect_all()
        for port in node.inputs:
            # Disconnect this input from any output that feeds it
            for other in self._nodes:
                if other is node:
                    continue
                for out in other.outputs:
                    out.disconnect(port)
        self._nodes.remove(node)

    @property
    def nodes(self) -> list[NodeBase]:
        return list(self._nodes)

    # ── Connection management ──────────────────────────────────────────────────

    def can_connect(
        self,
        src_node: NodeBase, output_idx: int,
        dst_node: NodeBase, input_idx: int,
    ) -> bool:
        """Return True if the two ports are type-compatible."""
        output_port = src_node.outputs[output_idx]
        input_port = dst_node.inputs[input_idx]
        return output_port.can_connect(input_port)

    def connect(
        self,
        src_node: NodeBase, output_idx: int,
        dst_node: NodeBase, input_idx: int,
    ) -> None:
        """Connect an output port to an input port.

        Raises TypeError if the port types are incompatible.
        Both nodes must have been added to the flow first.
        """
        output_port = src_node.outputs[output_idx]
        input_port = dst_node.inputs[input_idx]
        output_port.connect(input_port)

    def disconnect(
        self,
        src_node: NodeBase, output_idx: int,
        dst_node: NodeBase, input_idx: int,
    ) -> None:
        output_port = src_node.outputs[output_idx]
        input_port = dst_node.inputs[input_idx]
        output_port.disconnect(input_port)

    # ── Execution ──────────────────────────────────────────────────────────────

    @property
    def sources(self) -> list[SourceNodeBase]:
        """Return the flow's source nodes in registration order."""
        return [n for n in self._nodes if isinstance(n, SourceNodeBase)]

    @property
    def sinks(self) -> list[SinkNodeBase]:
        """Return the flow's sink nodes in registration order."""
        return [n for n in self._nodes if isinstance(n, SinkNodeBase)]

    def run(self) -> None:
        """Start every source node in the flow.

        A runnable flow must contain at least one source (an entry point
        that drives data through the graph) and at least one sink (a node
        that consumes the result). Multi-source flows are legal — e.g.
        three file sources feeding an RGB-join filter — so every source is
        started in registration order. In the push-based execution model,
        each start() propagates data downstream through connected ports.

        Raises:
            RuntimeError: if the flow has no source node or no sink node.
        """
        logger.info("Flow run started: %s", self._name)
        if not self.sources:
            raise RuntimeError("Flow has no source node; at least one is required")
        if not self.sinks:
            raise RuntimeError("Flow has no sink node; at least one is required")
        for source in self.sources:
            source.start()

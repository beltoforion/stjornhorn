from __future__ import annotations

import re

from core.node_base import NodeBase, SourceNodeBase
from core.port import InputPort, OutputPort


DEFAULT_FLOW_NAME: str = "Untitled flow"

# Characters that are invalid in filenames on at least one major platform
# (Windows is the strictest here), plus ASCII control characters.
_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_flow_name(name: str) -> str:
    """Return ``name`` stripped of filesystem-invalid characters and trimmed.

    Falls back to :data:`DEFAULT_FLOW_NAME` if the sanitized result is empty.
    """
    cleaned = _INVALID_FILENAME_CHARS.sub("", name).strip()
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

    def run(self) -> None:
        """Start all source nodes in registration order.

        The push-based execution model means calling start() on each source
        propagates data downstream automatically through connected ports.
        """
        for node in self._nodes:
            if isinstance(node, SourceNodeBase):
                node.start()

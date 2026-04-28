from __future__ import annotations

import logging
import re
from collections.abc import Iterator

from core.node_base import (
    NodeBase,
    SinkNodeBase,
    SourceNodeBase,
    set_current_flow_name,
)
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
        # Set by :meth:`request_stop` (typically from the UI thread when
        # the user clicks Stop). The execution loop checks the flag
        # between every interleave step and unwinds cleanly so nodes get
        # their normal ``after_run`` cleanup. Plain bool — relies on the
        # GIL making the read/write atomic; no lock needed for the
        # set-once / poll-many pattern used here.
        self._stop_requested: bool = False

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

    def request_stop(self) -> None:
        """Ask the running flow to stop at the next interleave step.

        Safe to call from any thread (the runner typically runs on a
        worker thread; the UI Stop button triggers this from the main
        thread). Sets a flag the execution loop polls between every
        step — each currently-executing node still finishes its
        in-flight frame, then the loop unwinds and ``after_run`` fires
        on every node so file handles / video captures release cleanly.
        """
        self._stop_requested = True

    @property
    def stop_requested(self) -> bool:
        """True between :meth:`request_stop` and the next :meth:`run`."""
        return self._stop_requested

    def run(self) -> None:
        """Drive every source node in the flow.

        A runnable flow must contain at least one source (an entry point
        that drives data through the graph). A sink is *not* required —
        a graph terminating at a Display (which surfaces the result via
        its inline preview) is a perfectly valid flow.

        Execution model:

        * Reactive (one-shot) sources fire first so their value is
          latched on downstream inputs before any streaming source
          starts pushing frames — otherwise a multi-input filter like
          Ncc would only process once, at the moment the one-shot
          source finally fires. See :meth:`SourceNodeBase.start` and
          :meth:`InputPort.clear` for the two halves of the latching
          mechanism.

        * Streaming sources are then **round-robined** via their
          :meth:`SourceNodeBase.iter_frames` generators: each iteration
          of the outer loop steps every active source once, so two
          streaming sources driving two param ports on the same node
          (e.g. two ``ValueSource``s feeding ``Overlay.angle`` and
          ``Overlay.xpos``) advance together and both animate. When a
          source's iterator is exhausted, its outputs are finished —
          :meth:`InputPort.clear`'s "retain after upstream finish"
          rule then latches its last value, so any still-running
          source can keep firing the dispatcher with the exhausted
          source's last value held in place.

        * The loop checks :attr:`stop_requested` between every step;
          on stop, every source's outputs are finished (idempotent)
          and ``after_run`` runs on every node so cleanup happens
          even after a partial run.

        Raises:
            RuntimeError: if the flow has no source node.
        """

        logger.info(f"Flow run requested: {self._name}")

        if not self.sources:
            raise RuntimeError("Flow has no source node; at least one is required")

        # Reset stop flag for this run so a previous Stop click doesn't
        # short-circuit the next Run.
        self._stop_requested = False

        # Publish the flow name so sinks can expand ``$flow_name$``
        # placeholders in their output paths. Cleared in ``finally``.
        set_current_flow_name(self._name)

        logger.info("initializing nodes")

        # initialize all nodes before starting any source
        for node in self._nodes:
            node.before_run()

        success: bool = False
        try:
            reactive = [s for s in self.sources if s.is_reactive]
            streaming = [s for s in self.sources if not s.is_reactive]

            # ── Phase 1: reactive sources ─────────────────────────────────
            for source in reactive:
                if self._stop_requested:
                    break
                source.start()

            # ── Phase 2: round-robin streaming sources ────────────────────
            # Each entry tracks (source, iterator). When an iterator
            # raises StopIteration, that source's outputs are finished
            # right away so its last value latches downstream.
            iters: list[tuple[SourceNodeBase, "Iterator[None]"]] = [
                (s, s.iter_frames()) for s in streaming
            ]

            while iters and not self._stop_requested:
                next_iters: list[tuple[SourceNodeBase, "Iterator[None]"]] = []
                for source, it in iters:
                    if self._stop_requested:
                        next_iters.append((source, it))
                        continue
                    try:
                        next(it)
                        next_iters.append((source, it))
                    except StopIteration:
                        for out in source.outputs:
                            out.finish()
                iters = next_iters

            # Stop / completion: close any still-open iterators (so
            # generator ``finally`` blocks fire — VideoCapture release,
            # etc.) and finish their outputs. ``OutputPort.finish`` is
            # idempotent so already-finished sources from natural
            # completion are unaffected.
            for source, it in iters:
                it.close()
                for out in source.outputs:
                    out.finish()

            # Belt-and-braces: cover any source whose ``iter_frames``
            # returned without yielding (zero-frame streaming source —
            # e.g. an inverted ValueSource range). ``finish`` is
            # idempotent.
            for source in self.sources:
                for out in source.outputs:
                    out.finish()

            success = not self._stop_requested
        finally:
            logger.info("Cleaning up nodes")

            for node in self._nodes:
                try:
                    node.after_run(success)
                except Exception:
                    logger.exception(f"Exception during cleanup of node {node.display_name} ({type(node).__name__})")

            set_current_flow_name(None)


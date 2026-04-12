from __future__ import annotations

from abc import ABC, abstractmethod

from core.io_data import IoData
from core.port import InputPort, OutputPort


class NodeBase(ABC):
    """Abstract base class for all nodes in a processing flow.

    Subclasses register their ports in __init__ via _add_input() and
    _add_output(), then implement process() to do their work.

    Execution model (push-based):
      - An OutputPort.send() pushes IoData to all connected InputPorts.
      - Each InputPort calls _signal_input_ready() on its owner node.
      - Once all inputs have data, process() is called automatically.
      - After process() returns, all inputs are cleared so the node is
        ready to accept the next batch of data.
      - If any arriving data is EndOfStream, _on_end_of_stream() is called
        instead of process().
    """

    def __init__(self, display_name: str) -> None:
        self._display_name = display_name
        self._inputs: list[InputPort] = []
        self._outputs: list[OutputPort] = []

    # ── Port registration (called from subclass __init__) ──────────────────────

    def _add_input(self, port: InputPort) -> None:
        self._inputs.append(port)

    def _add_output(self, port: OutputPort) -> None:
        self._outputs.append(port)

    # ── Public accessors ───────────────────────────────────────────────────────

    @property
    def display_name(self) -> str:
        return self._display_name

    @property
    def inputs(self) -> list[InputPort]:
        return self._inputs

    @property
    def outputs(self) -> list[OutputPort]:
        return self._outputs

    # ── Internal signal handling ───────────────────────────────────────────────

    def _signal_input_ready(self) -> None:
        """Called by an InputPort when it receives new data.

        Waits until all inputs have data, then dispatches to either
        _on_end_of_stream() or process().
        """
        if not all(p.has_data for p in self._inputs):
            return

        if any(p.data.is_end_of_stream() for p in self._inputs):
            self._on_end_of_stream()
        else:
            self.process()

        for p in self._inputs:
            p.clear()

    # ── Overridable behaviour ──────────────────────────────────────────────────

    @abstractmethod
    def process(self) -> None:
        """Read from self._inputs, compute, write to self._outputs."""
        ...

    def _on_end_of_stream(self) -> None:
        """Called when any input receives EndOfStream.

        Default: forward EndOfStream to all outputs so the signal propagates
        through the graph.  Override in SinkNodeBase where there is nothing to forward.
        """
        eos = IoData.end_of_stream()
        for port in self._outputs:
            port.send(eos)


# ── Concrete node base classes ─────────────────────────────────────────────────

class SourceNodeBase(NodeBase, ABC):
    """A node with outputs only.  Drives the pipeline by calling start()."""

    @abstractmethod
    def start(self) -> None:
        """Produce data and push it to output ports.

        Must send IoData.end_of_stream() on all outputs when done.
        """
        ...

    def process(self) -> None:
        raise RuntimeError("SourceNodeBase has no inputs; call start() instead")

    def _on_end_of_stream(self) -> None:
        pass  # Sources have no inputs, so this is never triggered


class SinkNodeBase(NodeBase, ABC):
    """A node with inputs only.  Consumes data (file write, display, etc.)."""

    @abstractmethod
    def process(self) -> None: ...

    def _on_end_of_stream(self) -> None:
        pass  # Sinks have no outputs to forward to

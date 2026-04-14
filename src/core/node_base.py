from __future__ import annotations

from abc import ABC, abstractmethod

from enum import Enum
from typing_extensions import override

from core.io_data import IoData
from core.port import InputPort, OutputPort


class NodeParamType(Enum):
    """Enumeration of parameter types for node parameters."""
    FILE_PATH = 0,
    FOLDER = 1,
    INT = 2,
    FLOAT = 3,
    STRING = 4,
    BOOL = 5,


class NodeParam:
    """Descriptor for a node parameter, used by the UI to generate controls."""
    def __init__(self, name: str, param_type: NodeParamType, metadata: dict) -> None:
        self.name : str = name
        self.param_type : NodeParamType = param_type
        self.metadata : dict = metadata


class NodeBase(ABC):
    """Abstract base class for all processing nodes.

    Concrete processing nodes subclass NodeBase directly.
    Source and sink nodes subclass SourceNodeBase or SinkNodeBase instead.

    Execution model (push-based):
      - SourceNodeBase.start() pushes IoData to its OutputPorts.
      - OutputPort.send() forwards data to all connected InputPorts.
      - Each InputPort notifies its owner node via _signal_input_ready().
      - Once all inputs have data, process() is invoked automatically.
      - Inputs are cleared after each process() call so the node is ready
        for the next frame.
      - If any input carries EndOfStream, _on_end_of_stream() is called
        instead of process(). By default this forwards EndOfStream to all
        outputs so the signal propagates to the end of the graph.
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
    @abstractmethod
    def params(self) -> list[NodeParam]:
        ...

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
        """Called by an InputPort whenever it receives new data.

        Waits until every input has data, then dispatches to process() or
        _on_end_of_stream() as appropriate, and clears all inputs afterwards.
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
        """Read from self._inputs, compute, and write results to self._outputs."""
        ...

    def _on_end_of_stream(self) -> None:
        """Called when any input receives EndOfStream.

        Default: forward EndOfStream to all outputs so the signal propagates
        through the graph. SinkNodeBase overrides this to do nothing.
        """
        eos = IoData.end_of_stream()
        for port in self._outputs:
            port.send(eos)


# ── Abstract base classes for sources and sinks ────────────────────────────────

class SourceNodeBase(NodeBase, ABC):
    """Abstract base class for source nodes.

    A source has outputs only — it produces data and drives the pipeline by
    implementing start(). Subclasses must call OutputPort.send() for each
    frame and send IoData.end_of_stream() on all outputs when done.
    """

    @abstractmethod
    def start(self) -> None:
        """Produce data and push it to output ports.

        Must send IoData.end_of_stream() on all outputs when done.
        """
        ...

    @override
    def process(self) -> None:
        raise RuntimeError("SourceNodeBase has no inputs; call start() instead")

    @override
    def _on_end_of_stream(self) -> None:
        pass  # Sources have no inputs, so this is never triggered


class SinkNodeBase(NodeBase, ABC):
    """Abstract base class for sink nodes.

    A sink has inputs only — it consumes data as a side effect (writing to
    a file, displaying to screen, etc.) and does not propagate data further.
    """

    @abstractmethod
    @override
    def process(self) -> None: ...

    @override
    def _on_end_of_stream(self) -> None:
        pass  # Sinks have no outputs to forward to

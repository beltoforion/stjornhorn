from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from enum import Enum
from typing import Callable, final, override

from core.io_data import IoData
from core.port import InputPort, OutputPort

logger = logging.getLogger(__name__)


# Optional observer invoked at the start of every NodeBase.process() call.
# A FlowRunner installs one of these to surface the currently-executing
# node on the UI (via a queued Qt signal). Module-level rather than
# per-instance because the push-based dispatcher doesn't otherwise carry
# a reference to the Flow / runner across node boundaries.
_process_observer: Callable[["NodeBase"], None] | None = None


def set_process_observer(callback: Callable[["NodeBase"], None] | None) -> None:
    """Install (or clear) the function invoked on every ``process()`` call.

    Pass ``None`` to clear. Thread-safety relies on the GIL making the
    module-attribute read/write atomic — good enough for the
    install-before-run / clear-after-run pattern used by
    :class:`core.flow_runner.FlowRunner`, not for rapid concurrent
    reconfiguration.
    """
    global _process_observer
    _process_observer = callback


class NodeParamType(Enum):
    """Enumeration of parameter types for node parameters."""
    FILE_PATH = 0,
    FOLDER = 1,
    INT = 2,
    FLOAT = 3,
    STRING = 4,
    BOOL = 5,
    ENUM = 6,


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
      - SourceNodeBase.start() drives each source by calling process(), which
        dispatches to process_impl(); a source's process_impl() pushes IoData
        to its OutputPorts.
      - OutputPort.send() forwards data to all connected InputPorts.
      - Each InputPort notifies its owner node via _signal_input_ready().
      - Once all inputs have data, process() is invoked automatically.
      - Inputs are cleared after each process() call so the node is ready
        for the next frame.
      - If any input carries EndOfStream, _on_end_of_stream() is called
        instead of process(). By default this forwards EndOfStream to all
        outputs so the signal propagates to the end of the graph.
    """

    #: Default palette section for this class. Subclasses may override to
    #: keep the ``section`` parameter optional for tests / ad-hoc nodes;
    #: production nodes should pass ``section=...`` explicitly so the
    #: NodeList palette picks it up via AST scanning.
    DEFAULT_SECTION: str = "Filters"

    def __init__(self, display_name: str, section: str | None = None) -> None:
        self._display_name = display_name
        self._section = section if section is not None else self.DEFAULT_SECTION
        self._inputs: list[InputPort] = []
        self._outputs: list[OutputPort] = []

    # ── Port registration (called from subclass __init__) ──────────────────────

    def _add_input(self, port: InputPort) -> None:
        self._inputs.append(port)
        # Wire the port so that data arriving at it drives this node's
        # dispatcher: _signal_input_ready checks whether every input has
        # data and, if so, invokes process() (or _on_end_of_stream()).
        port.set_on_data_received(self._signal_input_ready)

    def _add_output(self, port: OutputPort) -> None:
        self._outputs.append(port)

    # ── Param defaults ─────────────────────────────────────────────────────────

    def _apply_default_params(self) -> None:
        """Push every NodeParam's declared ``default`` metadata onto the
        matching instance attribute via the normal property setter.

        Call this at the end of a subclass ``__init__`` so the node's
        attributes match the values it advertises in :attr:`params` from
        the moment it is constructed — *before* any UI builder, save
        routine or scheduler can read stale data.

        Without this call, a node dropped onto the canvas and saved
        immediately serialises whatever placeholder its ``__init__`` set
        (e.g. ``Path()`` => ``"."``), not the value the params metadata
        promised.
        """
        for p in self.params:
            if "default" not in p.metadata:
                continue
            try:
                setattr(self, p.name, p.metadata["default"])
            except Exception:
                # A property setter may legitimately reject some defaults
                # (file dialogs validate paths, range setters clip, etc.).
                # Log and keep whatever value the subclass __init__
                # already wrote.
                logger.exception(
                    "Failed to apply declared default for %s.%s = %r",
                    type(self).__name__, p.name, p.metadata["default"],
                )

    # ── Public accessors ───────────────────────────────────────────────────────

    @property
    @abstractmethod
    def params(self) -> list[NodeParam]:
        ...

    @property
    def display_name(self) -> str:
        return self._display_name

    @property
    def section(self) -> str:
        """Palette section this node belongs to (e.g. ``"Processing"``)."""
        return self._section

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

    @final
    def process(self) -> None:
        """Dispatch to :meth:`process_impl` with logging and error handling.

        Subclasses should override :meth:`process_impl`, not this method, so
        that every node automatically benefits from the per-call tracing log
        and the common exception-logging path.
        """

        logger.debug(f"  - Executing {self._display_name} ({type(self).__name__})")

        observer = _process_observer
        if observer is not None:
            try:
                observer(self)
            except Exception:
                # An observer must never block node execution; log and
                # carry on so a buggy UI hook can't kill a flow.
                logger.exception("Process observer raised; ignoring")

        try:
            self.process_impl()
        except Exception:
            logger.exception(f"Exception in {type(self).__name__}.process_impl ({self._display_name})")
            raise

    @abstractmethod
    def process_impl(self) -> None:
        """Read from self._inputs, compute, and write results to self._outputs."""
        ...

    @final
    def before_run(self) -> None:
        """Hook invoked before a flow run starts, after all nodes are constructed.

        Default is no-op. Override this in nodes that need to do setup before
        processing starts (e.g. open a file, start a thread, etc.) and tear
        down in after_run().
        """
        try:
            self._before_run_impl()
        except Exception:
            logger.exception(f"Exception in {type(self).__name__}.before_run_impl ({self._display_name})")
            raise

    def _before_run_impl(self) -> None:
        """Prepare node data before a run."""
        logger.debug(f"_before_run_impl: {self._display_name} ({type(self).__name__})")

    @final
    def after_run(self, run_success: bool) -> None:
        """Hook invoked after a flow run ends, after all processing is done.

        Default is no-op. Override this in nodes that need to do teardown after
        processing ends (e.g. close a file, stop a thread, etc.) and set up in
        before_run().
        """
        try:
            self._after_run_impl(run_success)
        except Exception:
            logger.exception(f"Exception in {type(self).__name__}.after_run_impl ({self._display_name})")
            raise

    def _after_run_impl(self, run_success: bool) -> None:
        """Cleanup node data after a run"""
        logger.debug(f"_after_run_impl({run_success}): {self._display_name} ({type(self).__name__})")

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
    implementing :meth:`process_impl`. Subclasses must call OutputPort.send()
    for each frame and send IoData.end_of_stream() on all outputs when done.

    :meth:`start` is the public entry point used by :class:`core.flow.Flow`
    to kick a source off. It is final and simply routes through
    :meth:`process`, so source nodes benefit from the same per-node logging
    and observer hook that filters and sinks do (the UI uses that hook to
    highlight the currently-running node).

    Override :attr:`is_reactive` to ``True`` in sources that produce a single
    static result (e.g. a still image). The node editor will automatically
    re-run the flow whenever any parameter on any node changes, giving a
    live-coding feel.
    """

    DEFAULT_SECTION: str = "Sources"

    @property
    def is_reactive(self) -> bool:
        """Return True if this source should trigger an auto-run on any param change.

        Default is False (explicit Run button only).  Still-image sources
        override this to True so the flow re-executes whenever a parameter
        is edited.
        """
        return False

    @final
    def start(self) -> None:
        """Drive the source by invoking :meth:`process`.

        Kept as a distinct entry point so :meth:`core.flow.Flow.run` can
        tell source nodes apart from ordinary nodes without type-sniffing
        on every call.
        """
        self.process()

    @override
    def _on_end_of_stream(self) -> None:
        pass  # Sources have no inputs, so this is never triggered


class SinkNodeBase(NodeBase, ABC):
    """Abstract base class for sink nodes.

    A sink has inputs only — it consumes data as a side effect (writing to
    a file, displaying to screen, etc.) and does not propagate data further.
    """

    DEFAULT_SECTION: str = "Sinks"

    @abstractmethod
    @override
    def process_impl(self) -> None: ...

    @override
    def _on_end_of_stream(self) -> None:
        pass  # Sinks have no outputs to forward to

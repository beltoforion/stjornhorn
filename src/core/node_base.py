from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Iterator

from enum import Enum
from typing import Callable, final

from typing_extensions import override

from core.io_data import IoData, IoDataType
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
    """Descriptor for a node-level *constant* parameter.

    Used by sources and sinks for configuration that's not driveable
    from upstream — the file path on an :class:`ImageSource`, the
    output codec on a :class:`VideoSink`, etc. The UI renders these
    between the output and input port rows of the node body, with
    the same widget classes the inline-port editors use, and the
    caption rendered in italics so the user can tell a constant
    apart from a port-style param at a glance.

    Structurally compatible with :class:`~core.port.InputPort` so
    :func:`ui.param_widgets.build_param_widget` can dispatch on either
    kind without a type check: the widget reads ``.name``,
    ``.metadata`` and ``.upstream`` (always ``None`` on a constant —
    constants are never connection-driven).
    """

    def __init__(
        self,
        name: str,
        param_type: NodeParamType,
        default: object = None,
        metadata: dict | None = None,
    ) -> None:
        self.name: str = name
        # Stash the full metadata bundle the widgets read, with
        # ``param_type`` and ``default`` mirrored into it so the
        # widget builder's ``port.metadata.get("param_type")``
        # dispatch path keeps working unchanged.
        meta = dict(metadata) if metadata else {}
        meta.setdefault("param_type", param_type)
        meta.setdefault("default", default)
        self.metadata: dict = meta
        self.default_value: object = default

    @property
    def upstream(self) -> None:
        """Always ``None``; constants are not port-driven.

        Lets the param-widget code call ``editor.setEnabled(
        port.upstream is None)`` without having to special-case
        whether the editor is bound to an :class:`InputPort` or a
        :class:`NodeParam` — both expose the attribute.
        """
        return None


#: Maps a :class:`NodeParamType` to the :class:`~core.io_data.IoDataType`
#: that backs an editable parameter port. Numeric param types (INT,
#: FLOAT) collapse to a single ``SCALAR`` port type so any scalar
#: producer can drive any numeric param without a per-type bridge node;
#: the widget-side "render as int spinner vs float slider" hint stays
#: in the port's metadata under ``"param_type"``.
NODE_PARAM_TYPE_TO_PORT_TYPE: dict[NodeParamType, IoDataType] = {
    NodeParamType.INT:       IoDataType.SCALAR,
    NodeParamType.FLOAT:     IoDataType.SCALAR,
    NodeParamType.BOOL:      IoDataType.BOOL,
    NodeParamType.STRING:    IoDataType.STRING,
    NodeParamType.ENUM:      IoDataType.ENUM,
    NodeParamType.FILE_PATH: IoDataType.PATH,
    NodeParamType.FOLDER:    IoDataType.PATH,
}


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
      - Once all inputs have data, process() is invoked automatically and
        the inputs are cleared so the node is ready for the next frame.
      - Stream lifetime is a separate signal: OutputPort.finish() marks an
        output as done and propagates to every connected InputPort via its
        finish() method. When every input has finished, _on_finish() fires;
        the default implementation forwards finish() to all outputs so the
        signal propagates to the end of the graph.
    """

    #: Default palette section for this class. Subclasses may override to
    #: keep the ``section`` parameter optional for tests / ad-hoc nodes;
    #: production nodes should pass ``section=...`` explicitly so the
    #: NodeList palette picks it up via AST scanning.
    DEFAULT_SECTION: str = "Filters"

    #: Class-level descriptors collected by :meth:`__init_subclass__`.
    #: Populated lazily so the cycle ``params.py → node_base.py`` stays
    #: clean: the import only runs at subclass-creation time, after
    #: both modules have finished loading. Empty for subclasses that
    #: declare no descriptor-style params (legacy nodes that still use
    #: the explicit ``InputPort(...)`` + ``@property`` pattern).
    _param_descriptors: tuple = ()

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        # Late import — see the class-level docstring above.
        from core.params import _ParamBase
        descriptors: list[_ParamBase] = []
        for base in reversed(cls.__mro__):
            for attr_name, attr in vars(base).items():
                if isinstance(attr, _ParamBase) and attr not in descriptors:
                    descriptors.append(attr)
        cls._param_descriptors = tuple(descriptors)

    #: When True, the editor renders only the input rows up to the last
    #: connected port + 1 (the next "to-be-wired" tail). Lets a node
    #: declare a generous fixed pool of optional inputs (e.g. nine SCALAR
    #: slots on Math) without showing every empty row in the body. The
    #: backend port list is always the full pool so connection indices
    #: stay stable across save / load. Default: False — every input port
    #: is rendered, matching the behaviour of every existing node.
    SHOW_ONLY_USED_INPUTS: bool = False

    def __init__(self, display_name: str, section: str | None = None) -> None:
        self._display_name = display_name
        self._section = section if section is not None else self.DEFAULT_SECTION
        self._inputs: list[InputPort] = []
        self._outputs: list[OutputPort] = []
        self._params: list[NodeParam] = []
        self._skipped: bool = False
        # Initialise every descriptor's backing slot to its declared
        # default before subclass ``__init__`` runs, so ``self._<name>``
        # exists from the first line after ``super().__init__()``. The
        # default goes through the descriptor's ``__set__`` — full
        # coerce / validate / shape pipeline — so a misconfigured
        # default (e.g. an even value on an :class:`OddIntParam`)
        # fails loudly at construction time, and a valid one lands as
        # its canonical shaped form.
        for desc in self._param_descriptors:
            setattr(self, desc.name, desc.default)

    # ── Port registration (called from subclass __init__) ──────────────────────

    #: Meta keys the framework owns. An input port may not declare any
    #: of these as its name — :meth:`OutputPort.send` auto-stamps SCALAR
    #: input values into outgoing :class:`IoMeta` under the port name
    #: (refactor M13), so a port called ``frame_index`` would silently
    #: clobber the framework's per-port emit counter. Caught at port-
    #: declaration time so the conflict is impossible by construction.
    _RESERVED_META_KEYS: frozenset[str] = frozenset({
        "frame_index", "source_path", "timestamp",
    })

    def _add_input(self, port: InputPort) -> None:
        if port.name in self._RESERVED_META_KEYS:
            raise ValueError(
                f"Input port name {port.name!r} collides with a "
                f"framework-stamped IoMeta key. Reserved: "
                f"{sorted(self._RESERVED_META_KEYS)}"
            )
        self._inputs.append(port)
        # Wire the port so that any state change (data arrival or finish)
        # drives this node's dispatcher. ``add_listener`` instead of the
        # legacy ``set_on_state_changed`` so external observers (debug
        # hooks, UI indicators, tests) can attach their own listeners
        # later without clobbering the dispatcher hookup. Issue: M11.
        port.add_listener(self._signal_input_ready)

    def _add_output(self, port: OutputPort) -> None:
        self._outputs.append(port)
        # Back-reference so OutputPort.send() can walk the node's
        # SCALAR input ports and stamp their values into outgoing
        # meta. Refactor M13.
        port._owner_node = self

    def _add_param(self, param: NodeParam) -> None:
        """Register a constant parameter (not driveable from upstream).

        Used by sources and sinks for config that's set once by the
        user — file paths, codecs, fps, etc. The UI renders these
        between the output and input port rows with the same widget
        classes the port-style param widgets use, but with an italic
        caption (so the user can tell a constant apart from a port).
        """
        self._params.append(param)

    # ── Param defaults ─────────────────────────────────────────────────────────

    def _apply_default_params(self) -> None:
        """Auto-create the :class:`InputPort` (or :class:`NodeParam`
        registration) every class-level descriptor advertises.

        Call this at the end of a subclass ``__init__`` *after* the
        node has registered its hand-rolled ports (image inputs,
        outputs, etc.). Descriptor-driven ports land at the tail of
        ``self._inputs`` so the visual layout preserves the
        image-first / params-second convention.

        Each descriptor produces either:

        * A port-style :class:`InputPort` (default) — drivable from
          upstream, exposed inline as a port-row widget.
        * A constant-style entry on :attr:`params` — for descriptors
          declared with ``constant=True``. The descriptor object
          itself satisfies the NodeParam read interface
          (``name`` / ``metadata`` / ``default_value`` / ``upstream``
          — see :class:`core.params._ParamBase`) so the UI's existing
          ``node.params`` dispatch picks it up without a wrapper.

        Default *values* are written by :meth:`__init__` (which calls
        each descriptor's full ``__set__`` pipeline before the
        subclass body runs); this method does not touch attribute
        state.

        The existing-name guards make the method idempotent — calling
        it twice doesn't double-add a port — and tolerate hand-rolled
        ports that happen to share a name with a descriptor (the
        hand-rolled one wins).
        """
        existing_input_names = {p.name for p in self._inputs}
        existing_param_names = {p.name for p in self._params}
        for desc in self._param_descriptors:
            if desc.constant:
                if desc.name in existing_param_names:
                    continue
                self._params.append(desc)
            else:
                if desc.name in existing_input_names:
                    continue
                self._add_input(desc.make_port())

    # ── Public accessors ───────────────────────────────────────────────────────

    @property
    def params(self) -> list[NodeParam]:
        """The constant parameters this node exposes to the UI.

        Used by sources and sinks for config that's set inline by the
        user (file paths, codec selections, fps) and isn't driveable
        from upstream. The UI renders these between the output and
        input port rows of the node body, with an italic caption to
        differentiate them from port-style param widgets sitting on
        input rows.

        For the editable *port* inputs (``param_type`` metadata), see
        :attr:`param_input_ports`.
        """
        return list(self._params)

    @property
    def param_input_ports(self) -> list[InputPort]:
        """The editable input ports (port-style params) this node exposes.

        Returns the subset of ``self._inputs`` whose ``metadata``
        carries a ``"param_type"`` key. The UI builds an inline widget
        on each port's row; each port carries everything the widget
        needs (``name``, ``metadata["param_type"]``, ``metadata`` for
        widget hints, ``upstream`` for the connected/disconnected
        state).

        Image-flow inputs leave ``metadata`` empty and are filtered out
        so the renderer doesn't draw a widget for an image socket.
        """
        return [
            port for port in self._inputs
            if "param_type" in port.metadata
        ]

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

    # ── Skip (pass-through) state ──────────────────────────────────────────────

    @property
    def is_skippable(self) -> bool:
        """True if this node can be bypassed without breaking type safety.

        Mirrors Blender's "mute" semantics: skipping shorts each output
        to whichever input has a type-compatible payload, so the node
        is skippable as long as *at least one* input/output pair
        exists with overlapping types. Param-style ports (SCALAR /
        BOOL / ENUM / PATH auto-created from NodeParams) carry override
        values rather than data flow and don't overlap an image
        output, so they're naturally invisible to skip detection —
        adding more of them to a node never breaks its skippability.
        Sources (no inputs) and sinks (no outputs) are never skippable.
        """
        if not self._inputs or not self._outputs:
            return False
        return any(
            inp.accepted_types & out.emits
            for inp in self._inputs
            for out in self._outputs
        )

    @property
    def skipped(self) -> bool:
        """True if this node is currently bypassed (inputs forwarded to outputs)."""
        return self._skipped

    @skipped.setter
    def skipped(self, value: bool) -> None:
        flag = bool(value)
        if flag and not self.is_skippable:
            raise ValueError(
                f"{type(self).__name__} ({self._display_name}) is not skippable"
            )
        old = self._skipped
        self._skipped = flag
        if old != flag:
            self._on_skipped_changed(flag)

    def _on_skipped_changed(self, skipped: bool) -> None:
        """Hook for subclasses; called whenever :attr:`skipped` flips.

        Default: no-op. Override to react to the transition — e.g. a
        node that buffers frames internally can drain its buffer
        when entering skip mode so downstream sinks don't sit on
        stale data while the user toggles skipping back and forth.
        """

    # ── Internal signal handling ───────────────────────────────────────────────

    def _signal_input_ready(self) -> None:
        """Called by an InputPort whenever its state changes.

        Fires :meth:`process` as soon as every *waited-on* input has data
        AND at least one of them is *fresh* (received since the last
        dispatch). The freshness gate matters for nodes whose param-style
        ports retain their data across :meth:`InputPort.clear`: without
        it, a sibling input's :meth:`finish` would re-fire the
        dispatcher against the latched stale values and emit a duplicate
        composite frame.

        Clears every input after :meth:`process`, so the node is ready
        for the next frame. Param-style and finished-upstream ports
        keep their *data* across the clear (their :attr:`is_fresh` is
        still flipped to ``False``).

        An optional input counts as waited-on only while it has an
        upstream connected. An unconnected optional port is skipped
        entirely — the node fires without it, and its payload (if any)
        is cleared along with the rest. Once connected, the port
        behaves like a required input so a producer that emits a
        matching-frame alpha plane (e.g. :class:`RgbaSplit` →
        :class:`RgbaJoin`) isn't raced by the dispatcher firing on
        the required inputs alone.

        Fires :meth:`_on_finish` once every waited-on input has
        finished, so the lifecycle signal propagates down the graph
        even when an optional input is dangling unconnected. Inputs
        marked ``hold_last`` are excluded from the finish check —
        they're parameters carried alongside a streaming clock, not
        lifecycle drivers, so a held one-shot source going quiet must
        not pull the consumer down with it.
        """
        waited = [
            p for p in self._inputs
            if not p.optional or p.upstream is not None
        ]

        if (
            all(p.has_data for p in waited)
            and any(p.is_fresh for p in waited)
        ):
            self.process()
            for p in self._inputs:
                p.clear()
            return

        clocks = [p for p in waited if not p.hold_last]
        if clocks and all(p.finished for p in clocks):
            self._on_finish()

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
            # Populate self._<port_name> from any port currently driven
            # by an upstream, so process_impl can read its attributes
            # uniformly (no manual ``port.data.payload.item() if has_data
            # else self._x`` branch in every node). Restored after the
            # call so the user-set value the slider committed isn't
            # overwritten permanently by a streamed frame.
            snapshot = self._populate_port_driven_attributes()
            try:
                if self._skipped:
                    self._process_skipped()
                else:
                    self.process_impl()
            finally:
                self._restore_port_driven_attributes(snapshot)
        except Exception:
            logger.exception(f"Exception in {type(self).__name__}.process_impl ({self._display_name})")
            raise

    # ── Port-driven attribute population ────────────────────────────────────────

    def _populate_port_driven_attributes(self) -> dict[str, object]:
        """Write the current upstream value of every connected
        param-style input port into ``self._<port_name>`` and return
        a snapshot of the previous values for
        :meth:`_restore_port_driven_attributes`.

        Image / data-flow inputs are skipped — the gate is the
        ``"param_type"`` metadata key, which only param-style ports
        (the ones a descriptor auto-creates) carry. Image inputs read
        via ``self.inputs[i].data`` rather than via a Python
        attribute, so they have no field to populate.

        Assignment goes through the public name
        (``setattr(self, 'angle', value)``) so the descriptor's
        ``__set__`` runs and applies its validation / clamping /
        shaping as if the user had moved the slider. On any error
        during populate (e.g. a descriptor rejecting a streamed
        value), already-applied writes are rolled back via the
        partial snapshot so the node's state stays consistent.
        """
        snapshot: dict[str, object] = {}
        try:
            for port in self._inputs:
                if not port.has_data:
                    continue
                if "param_type" not in port.metadata:
                    continue
                attr_name = f"_{port.name}"
                # Dynamic ports (e.g. Math's ``v_1`` pool) carry the
                # ``param_type`` metadata so the UI renders an inline
                # widget, but they're declared in ``__init__`` rather
                # than as class-level descriptors, so no ``_<name>``
                # backing slot exists. The owning node reads such
                # ports directly via ``getattr(self, port.name, …)``
                # in ``process_impl``; the populate path simply skips
                # them.
                if not hasattr(self, attr_name):
                    continue
                snapshot[attr_name] = getattr(self, attr_name)
                value = self._extract_driven_value(port.data)
                setattr(self, port.name, value)
        except Exception:
            self._restore_port_driven_attributes(snapshot)
            raise
        return snapshot

    def _restore_port_driven_attributes(self, snapshot: dict[str, object]) -> None:
        """Write each snapshotted value back to its private attribute,
        bypassing the public ``@setter`` since the original value was
        already validated when the user (or flow loader) first set it."""
        for attr_name, value in snapshot.items():
            object.__setattr__(self, attr_name, value)

    @staticmethod
    def _extract_driven_value(data: IoData) -> object:
        """Convert an :class:`IoData` payload into the Python value to
        write into the backing attribute. SCALAR is unwrapped via
        ``.item()`` so a downstream property setter that does
        ``float(value)`` keeps working (numpy 0-d arrays already
        behave like floats but ``.item()`` makes the type explicit).
        Every other kind passes the payload through unchanged."""
        if data.type is IoDataType.SCALAR:
            return data.payload.item()
        return data.payload

    def _process_skipped(self) -> None:
        """Forward each output port from the first type-compatible
        input port (Blender mute semantics).

        For each output, picks the earliest input whose
        ``accepted_types`` intersect the output's ``emits`` set, then
        forwards that input's IoData. Outputs without a matching input
        are simply not driven this frame (they keep whatever they last
        emitted, if any). Param-style ports (SCALAR / BOOL / etc.)
        won't typically share types with image outputs, so they're
        naturally ignored by skip — which is the desired behaviour:
        skipping is about data-flow short-circuiting, not param
        forwarding.
        """
        for out in self._outputs:
            match = next(
                (inp for inp in self._inputs if inp.accepted_types & out.emits),
                None,
            )
            if match is not None and match.has_data:
                out.send(match.data)

    @abstractmethod
    def process_impl(self) -> None:
        """Read from self._inputs, compute, and write results to self._outputs."""
        ...

    @final
    def before_run(self) -> None:
        """Hook invoked before a flow run starts, after all nodes are constructed.

        Resets every port's lifecycle state so ``finished`` flags from a
        previous run don't block this one (otherwise a source's first
        ``send()`` raises ``send() called after finish()``), then
        dispatches to :meth:`_before_run_impl` for subclass setup.
        """
        for port in self._inputs:
            port.reset()
        for port in self._outputs:
            port.reset()
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

    def _on_finish(self) -> None:
        """Called when every input has finished.

        Default: forward :meth:`~core.port.OutputPort.finish` to all
        outputs so the signal propagates through the graph.
        :class:`SinkNodeBase` overrides this to do nothing.
        """
        for port in self._outputs:
            port.finish()

    def on_flow_loaded(self) -> None:
        """Hook fired once after the node has been deserialized into a flow.

        Called by :func:`ui.flow_io.load_flow_into` for every node after
        all params are restored, the node is in the scene, and connections
        have been wired. The default is a no-op; override it for
        cache-warming work that would otherwise stall the first paint —
        :class:`~nodes.sources.video_source.VideoSource` reads its frame
        count here, :class:`~nodes.sources.directory_source.DirectorySource`
        counts files. Anything raised is caught at the caller and logged
        so a single bad node doesn't sink the whole load.
        """


# ── Abstract base classes for sources and sinks ────────────────────────────────

class SourceNodeBase(NodeBase, ABC):
    """Abstract base class for source nodes.

    A source has outputs only — it produces data and drives the pipeline by
    implementing :meth:`process_impl`. Subclasses call ``OutputPort.send()``
    for each frame and return when done; :class:`core.flow.Flow.run`
    signals end-of-stream centrally by calling ``OutputPort.finish()`` on
    every source output after every source has returned, so sources never
    emit a lifecycle signal inline with data.

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

    def iter_frames(self) -> Iterator[None]:
        """Yield once per frame this source emits.

        Default implementation: one-shot — call :meth:`process` once and
        yield once. Reactive sources (e.g. :class:`ImageSource`) and any
        source whose ``process_impl`` emits everything in a single call
        are happy with the default.

        Streaming sources (counters, video readers, directory walkers)
        should override this to be a true generator that ``yield``s once
        per emitted frame, so :meth:`core.flow.Flow.run` can round-robin
        multiple streaming sources frame-by-frame instead of running
        each to completion sequentially. Without round-robin, two
        streaming sources driving the same downstream node would only
        produce one composite frame — the first source drains entirely
        before the second sends its first value, so the dispatcher only
        sees all-inputs-have-data once.
        """
        self.process()
        yield

    def tick_count(self) -> int | None:
        """Number of frames this source will emit, or ``None`` if unknown.

        Used by the node header to display a frame count badge. Reactive
        (one-shot) sources return ``1``; streaming sources that know their
        count return it; sources whose count depends on runtime state
        (file size, directory contents) return ``None``.
        """
        return None

    @final
    def start(self) -> None:
        """Drive the source by draining :meth:`iter_frames`.

        Kept as a distinct entry point so :meth:`core.flow.Flow.run` can
        tell source nodes apart from ordinary nodes without type-sniffing
        on every call. The flow runner uses :meth:`iter_frames` directly
        for streaming-source round-robin; ``start()`` remains the
        all-at-once drain path used by tests and other one-shot callers.

        Reactive sources emit a single value, so their outputs are
        finished right after the iterator drains. Combined with the
        latching behaviour in :meth:`core.port.InputPort.clear`, that
        lets the one-shot value persist on downstream inputs while
        other (streaming) sources keep pushing frames.
        """
        for _ in self.iter_frames():
            pass
        if self.is_reactive:
            for out in self._outputs:
                out.finish()

    @override
    def _on_finish(self) -> None:
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
    def _on_finish(self) -> None:
        pass  # Sinks have no outputs to forward to

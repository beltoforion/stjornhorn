from __future__ import annotations

from typing import Callable, TYPE_CHECKING

from core.io_data import IoData

if TYPE_CHECKING:
    pass


class InputPort:
    """A typed input connection point on a node.

    ``accepted_types`` declares which :class:`~core.io_data.IoDataType`
    values this port can receive.

    ``on_state_changed`` is a zero-argument callback invoked each time
    the port's state changes — either because new data was ``receive``-d
    or because the upstream signalled :meth:`finish`. Nodes use it to
    drive their dispatch logic.

    An input port can be fed by **at most one** upstream
    :class:`OutputPort` — fan-in is not supported. The binding is
    maintained by :meth:`OutputPort.connect` / :meth:`OutputPort.disconnect`
    and exposed read-only through :attr:`upstream`.

    Stream lifetime is expressed via :meth:`finish` rather than via a
    payload value, so :meth:`receive` only ever carries real data.

    An ``optional`` port does not block the owning node's dispatcher:
    the node fires as soon as every *required* input has data, regardless
    of whether the optional port is connected or has produced anything.
    Node implementations inspect :attr:`has_data` on an optional port to
    decide whether to consume it.

    ``default_value`` is the literal value used when the port has no
    upstream connection — the seed that the Blender-style socket UI
    edits inline. Loosely typed (``object | None``) because every
    payload kind shares this slot.

    ``metadata`` is a free-form dict that hosts widget hints
    (``min``/``max``/``step``/``enum``/``filter``/…) plus a
    ``"param_type"`` key for ports that should render an inline
    editor. The UI iterates :attr:`NodeBase.params` to find the
    subset of inputs with a ``"param_type"`` entry and renders one
    widget per port; image-flow inputs leave metadata empty and stay
    socket-only.
    """

    def __init__(
        self,
        name: str,
        accepted_types: set[IoDataType],
        on_state_changed: Callable[[], None] | None = None,
        optional: bool = False,
        default_value: object | None = None,
        metadata: dict | None = None,
    ) -> None:
        self.name = name
        self.accepted_types: frozenset[IoDataType] = frozenset(accepted_types)
        self.optional: bool = optional
        self._on_state_changed = on_state_changed
        self._data: IoData | None = None
        self._finished: bool = False
        self._upstream: "OutputPort | None" = None
        self._default_value: object | None = default_value
        # Copy so a caller's literal dict can't mutate the port's metadata
        # later (and vice versa) — common gotcha when the same default
        # dict is reused across multiple node constructions.
        self.metadata: dict = dict(metadata) if metadata else {}

    @property
    def has_data(self) -> bool:
        return self._data is not None

    @property
    def data(self) -> IoData:
        if self._data is None:
            raise RuntimeError(f"Input port '{self.name}' has no data yet")
        return self._data

    @property
    def finished(self) -> bool:
        """True once :meth:`finish` has been called — no more data will arrive."""
        return self._finished

    @property
    def upstream(self) -> "OutputPort | None":
        """The OutputPort currently feeding this input, if any."""
        return self._upstream

    @property
    def default_value(self) -> object | None:
        """The literal value used when no upstream is connected.

        Settable so the UI can update the seed in place without
        re-creating the port.
        """
        return self._default_value

    @default_value.setter
    def default_value(self, value: object | None) -> None:
        self._default_value = value

    @property
    def has_default(self) -> bool:
        """True when a literal default has been set (incl. falsy values)."""
        return self._default_value is not None

    def receive(self, data: IoData) -> None:
        if data.type not in self.accepted_types:
            raise TypeError(
                f"Port '{self.name}' accepts {set(self.accepted_types)} "
                f"but received {data.type}"
            )
        if self._finished:
            raise RuntimeError(
                f"Port '{self.name}' received data after finish()"
            )
        self._data = data
        if self._on_state_changed is not None:
            self._on_state_changed()

    def finish(self) -> None:
        """Mark this input as finished; no further data will arrive.

        Fires the state-changed callback exactly like :meth:`receive` so
        the owning node's dispatcher re-evaluates and can forward the
        lifecycle signal downstream once every input has finished.
        """
        if self._finished:
            return
        self._finished = True
        if self._on_state_changed is not None:
            self._on_state_changed()

    def set_on_state_changed(self, callback: Callable[[], None]) -> None:
        """Set the callback invoked each time this port's state changes
        (data arrival or finish). :class:`~core.node_base.NodeBase` uses
        this during port registration to wire every input to the owning
        node's dispatcher.
        """
        self._on_state_changed = callback

    def clear(self) -> None:
        """Drop buffered data so the owning node can receive the next frame.

        Data from an upstream that has already called :meth:`finish` is
        retained (latched) rather than cleared. That lets a one-shot
        source — e.g. :class:`~nodes.sources.image_source.ImageSource`
        wired into the ``template`` input of
        :class:`~nodes.filters.ncc.Ncc` — stay available while another
        (streaming) source continues to push frames through the other
        input.
        """
        if self._finished:
            return
        self._data = None

    def reset(self) -> None:
        """Clear data and lifecycle state so this port can drive a new run.

        Called by :meth:`~core.node_base.NodeBase.before_run` for every
        input on every node, so a flow can be executed repeatedly
        without stale ``finished`` flags blocking later runs.
        """
        self._data = None
        self._finished = False


class OutputPort:
    """A typed output connection point on a node.

    ``emits`` declares which :class:`~core.io_data.IoDataType` values this
    port will send. The UI and :class:`~core.flow.Flow` use this to
    validate connections before they are made: a connection is only
    allowed if the output's ``emits`` set and the input's
    ``accepted_types`` set have at least one type in common.

    Fan-out is allowed — one output can drive any number of inputs — but
    each input may have at most one upstream output (enforced by
    :meth:`connect`).

    Stream lifetime is a separate channel: :meth:`finish` signals "no
    more data will be sent", and propagates to every connected input.
    """

    def __init__(self, name: str, emits: set[IoDataType]) -> None:
        self.name = name
        self.emits: frozenset[IoDataType] = frozenset(emits)
        self._connections: list[InputPort] = []
        # Last IoData the port emitted via send(); None until the first
        # send. Used by the viewer panel to show the current output of a
        # node without needing the flow to re-run on every selection.
        self._last_emitted: IoData | None = None
        self._finished: bool = False

    # ── Connection management ──────────────────────────────────────────────────

    def can_connect(self, input_port: InputPort) -> bool:
        """Return True if type sets are compatible and the input is free
        (not already fed by another output)."""
        if not (self.emits & input_port.accepted_types):
            return False
        if input_port.upstream is not None and input_port.upstream is not self:
            return False
        return True

    def connect(self, input_port: InputPort) -> None:
        if not (self.emits & input_port.accepted_types):
            raise TypeError(
                f"Cannot connect output '{self.name}' (emits {set(self.emits)}) "
                f"to input '{input_port.name}' (accepts {set(input_port.accepted_types)})"
            )
        if input_port.upstream is not None and input_port.upstream is not self:
            raise TypeError(
                f"Input '{input_port.name}' is already connected to "
                f"'{input_port.upstream.name}'. Disconnect it first."
            )
        if input_port not in self._connections:
            self._connections.append(input_port)
            input_port._upstream = self

    def disconnect(self, input_port: InputPort) -> None:
        if input_port in self._connections:
            self._connections.remove(input_port)
            if input_port.upstream is self:
                input_port._upstream = None

    def disconnect_all(self) -> None:
        for input_port in self._connections:
            if input_port.upstream is self:
                input_port._upstream = None
        self._connections.clear()

    @property
    def connections(self) -> list[InputPort]:
        return list(self._connections)

    @property
    def last_emitted(self) -> IoData | None:
        """Most recent ``IoData`` passed to :meth:`send`, or ``None`` if the
        port has not emitted anything yet (or since the port was cleared)."""
        return self._last_emitted

    def clear_last_emitted(self) -> None:
        self._last_emitted = None

    @property
    def finished(self) -> bool:
        """True once :meth:`finish` has been called on this output."""
        return self._finished

    # ── Data flow ──────────────────────────────────────────────────────────────

    def send(self, data: IoData) -> None:
        if self._finished:
            raise RuntimeError(
                f"Output '{self.name}' send() called after finish()"
            )
        self._last_emitted = data
        for port in self._connections:
            port.receive(data)

    def finish(self) -> None:
        """Signal that no more data will be sent on this output.

        Propagates to every connected input via :meth:`InputPort.finish`
        so the downstream dispatcher can react. Idempotent.
        """
        if self._finished:
            return
        self._finished = True
        for port in self._connections:
            port.finish()

    def reset(self) -> None:
        """Clear lifecycle state so this port can drive a new run.

        Called by :meth:`~core.node_base.NodeBase.before_run` for every
        output on every node. The last-emitted cache is preserved so
        viewers still show the previous run's output until the new run
        produces something fresh.
        """
        self._finished = False

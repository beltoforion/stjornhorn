from __future__ import annotations

from typing import Callable

from core.io_data import IoData, IoDataType


class InputPort:
    """A typed input connection point on a node.

    accepted_types declares which IoDataType values this port can receive.
    EndOfStream is always accepted regardless of accepted_types — it is a
    control signal, not payload data.

    on_data_received is a zero-argument callback invoked each time new data
    arrives; nodes use it to trigger their processing logic.
    """

    def __init__(
        self,
        name: str,
        accepted_types: set[IoDataType],
        on_data_received: Callable[[], None] | None = None,
    ) -> None:
        self.name = name
        self.accepted_types: frozenset[IoDataType] = frozenset(accepted_types)
        self._on_data_received = on_data_received
        self._data: IoData | None = None

    @property
    def has_data(self) -> bool:
        return self._data is not None

    @property
    def data(self) -> IoData:
        if self._data is None:
            raise RuntimeError(f"Input port '{self.name}' has no data yet")
        return self._data

    def receive(self, data: IoData) -> None:
        if not data.is_end_of_stream() and data.type not in self.accepted_types:
            raise TypeError(
                f"Port '{self.name}' accepts {set(self.accepted_types)} "
                f"but received {data.type}"
            )
        self._data = data
        if self._on_data_received is not None:
            self._on_data_received()

    def set_on_data_received(self, callback: Callable[[], None]) -> None:
        """Set the callback invoked each time new data arrives at this port.

        NodeBase uses this during port registration to wire every input to
        the owning node's ``_signal_input_ready`` dispatcher.
        """
        self._on_data_received = callback

    def clear(self) -> None:
        self._data = None


class OutputPort:
    """A typed output connection point on a node.

    emits declares which IoDataType values this port will send.  The UI and
    Flow use this to validate connections before they are made: a connection
    is only allowed if the output's emits set and the input's accepted_types
    set have at least one type in common.
    """

    def __init__(self, name: str, emits: set[IoDataType]) -> None:
        self.name = name
        self.emits: frozenset[IoDataType] = frozenset(emits)
        self._connections: list[InputPort] = []
        # Last IoData the port emitted via send(); None until the first
        # send. Used by the viewer panel to show the current output of a
        # node without needing the flow to re-run on every selection.
        self._last_emitted: IoData | None = None

    # ── Connection management ──────────────────────────────────────────────────

    def can_connect(self, input_port: InputPort) -> bool:
        """Return True if type sets are compatible."""
        return bool(self.emits & input_port.accepted_types)

    def connect(self, input_port: InputPort) -> None:
        if not self.can_connect(input_port):
            raise TypeError(
                f"Cannot connect output '{self.name}' (emits {set(self.emits)}) "
                f"to input '{input_port.name}' (accepts {set(input_port.accepted_types)})"
            )
        if input_port not in self._connections:
            self._connections.append(input_port)

    def disconnect(self, input_port: InputPort) -> None:
        if input_port in self._connections:
            self._connections.remove(input_port)

    def disconnect_all(self) -> None:
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

    # ── Data flow ──────────────────────────────────────────────────────────────

    def send(self, data: IoData) -> None:
        # Only cache real payload; EOS is a control signal and should not
        # overwrite the last meaningful result the viewer wants to display.
        if not data.is_end_of_stream():
            self._last_emitted = data
        for port in self._connections:
            port.receive(data)

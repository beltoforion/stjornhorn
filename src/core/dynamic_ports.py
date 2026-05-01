"""Dynamic input-port groups.

A :class:`DynamicInputGroup` manages an append-only list of homogeneous
optional input ports on a :class:`~core.node_base.NodeBase`. The group
keeps exactly one trailing unconnected port at all times: as soon as the
user wires up the tail port, a new empty tail is appended (capped at
:attr:`max_count`). Wiring a port disconnected leaves the topology
unchanged so saved-flow round-trips are stable — index ``N`` keeps
referring to the same port slot across save / load.

Three nodes use this helper:

* :class:`~nodes.filters.math.Math` exposes ``v[1]``…``v[9]`` SCALAR
  inputs that the user references inside the expression.
* :class:`~nodes.filters.join_datasets.JoinDatasets` exposes
  ``dataset[1]``…``dataset[9]`` DATASET inputs.
* :class:`~nodes.filters.mosaic.Mosaic` exposes ``image[1]``…``image[9]``
  IMAGE inputs whose order is referenced by the layout descriptor.

The serialised flow stores the current port count per group so the
loader can recreate the right number of ports before wiring connections
by index.
"""
from __future__ import annotations

from typing import Callable

from core.io_data import IoDataType
from core.node_base import NodeBase
from core.port import InputPort

#: Hard cap shared across every node that uses a DynamicInputGroup.
#: Math expressions, mosaic layout descriptors and dataset-join column
#: lists all become unwieldy past nine slots, and a single shared cap
#: keeps the UX uniform — there is no node where eleven inputs would
#: read better than nine.
MAX_DYNAMIC_INPUTS: int = 9


class DynamicInputGroup:
    """Append-only group of optional input ports on a node.

    The first port is created at construction. After every connect /
    disconnect transition on any port in the group, the helper appends
    a new tail port if (a) the previous tail just became connected and
    (b) the group is below :attr:`max_count`. Disconnects do not trim;
    the port list only grows. This keeps connection-by-index stable
    across save / load and across user edits.

    The owning node is expected to declare exactly one group per
    homogeneous input cluster. Mixing dynamic and static input ports on
    the same node is allowed — the group only manages the ports it
    created.
    """

    def __init__(
        self,
        owner: NodeBase,
        *,
        name_template: str,
        accepted_types: set[IoDataType],
        metadata: dict | None = None,
        max_count: int = MAX_DYNAMIC_INPUTS,
    ) -> None:
        """Initialise the group and create its first input port.

        ``name_template`` is a :py:meth:`str.format` template that
        receives the 1-based slot index as ``i`` (e.g. ``"v[{i}]"``).
        ``accepted_types`` and ``metadata`` are forwarded to every
        :class:`InputPort` the group creates. ``max_count`` caps the
        number of ports the group will ever own; defaults to
        :data:`MAX_DYNAMIC_INPUTS`.
        """
        if max_count < 1:
            raise ValueError(f"max_count must be >= 1 (got {max_count})")
        self._owner: NodeBase = owner
        self._name_template: str = name_template
        self._accepted_types: set[IoDataType] = set(accepted_types)
        self._metadata: dict | None = dict(metadata) if metadata else None
        self._max_count: int = max_count
        self._ports: list[InputPort] = []
        self._append_port()

    # ── Public read interface ──────────────────────────────────────────────────

    @property
    def ports(self) -> list[InputPort]:
        """Snapshot of the group's input ports, in slot order (1..N)."""
        return list(self._ports)

    @property
    def count(self) -> int:
        """Number of ports currently in the group."""
        return len(self._ports)

    @property
    def max_count(self) -> int:
        """The cap on how many ports this group will ever own."""
        return self._max_count

    # ── Loader hook ────────────────────────────────────────────────────────────

    def ensure_at_least(self, n: int) -> None:
        """Grow the group so it has at least *n* ports.

        Called by :func:`ui.flow_io.load_flow_into` before wiring saved
        connections, so a connection that references slot ``k`` finds
        the corresponding port already present. Capped at
        :attr:`max_count`; values above the cap are silently truncated
        (the loader logs and skips out-of-range connections via the
        same path it uses for malformed entries).
        """
        target = min(int(n), self._max_count)
        while len(self._ports) < target:
            self._append_port()

    # ── Internals ──────────────────────────────────────────────────────────────

    def _append_port(self) -> None:
        """Create one port at the next slot and register it with the owner.

        Hooked up so a connect / disconnect on the *new* tail triggers
        :meth:`_on_connection_changed`, which is what drives further
        growth. Notifies the owner's ports-changed listeners so the UI
        rebuilds its port-row widgets.
        """
        idx = len(self._ports) + 1
        port = InputPort(
            self._name_template.format(i=idx),
            self._accepted_types,
            optional=True,
            metadata=dict(self._metadata) if self._metadata else None,
        )
        port.add_connection_listener(self._on_connection_changed)
        self._ports.append(port)
        self._owner._add_input(port)
        self._owner._notify_ports_changed()

    def _on_connection_changed(self) -> None:
        """Handle a connect / disconnect on any port in the group.

        Growth rule: when the *tail* port becomes connected and the
        group is below its cap, append a new empty tail. Disconnects
        never trim — the port list is append-only by design (see class
        docstring).
        """
        if not self._ports:
            return  # safety: empty group can't be tail-checked
        tail = self._ports[-1]
        if tail.upstream is None:
            return  # disconnect, or a non-tail port — nothing to do
        if len(self._ports) >= self._max_count:
            return  # at cap
        self._append_port()


def find_dynamic_groups(node: NodeBase) -> dict[str, DynamicInputGroup]:
    """Return ``{group_name: group}`` for every dynamic group on *node*.

    Looked up via the ``_dynamic_input_groups`` attribute that nodes
    publish when they construct one or more :class:`DynamicInputGroup`
    instances. The attribute maps a stable string key (used by the
    flow-file serialiser) to the group; nodes with no dynamic groups
    return an empty dict so callers can iterate uniformly.
    """
    return dict(getattr(node, "_dynamic_input_groups", {}))

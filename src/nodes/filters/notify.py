from __future__ import annotations

from enum import IntEnum

from typing_extensions import override

from core import notifications
from core.io_data import IMAGE_TYPES
from core.node_base import NodeBase
from core.params import EnumParam, StringParam
from core.port import InputPort, OutputPort


class NotifySeverity(IntEnum):
    """Severity choice for the :class:`Notify` node."""
    #: Emit a neutral status message via :mod:`core.notifications`. Run
    #: continues; the message surfaces in the floating banner (blue).
    INFO = 0
    #: Emit a warning. Run continues; the warning surfaces in the
    #: floating banner (amber).
    WARNING = 1
    #: Raise a ``RuntimeError`` carrying the configured message. Run
    #: aborts; the banner shows the standard red error.
    ERROR = 2


class Notify(NodeBase):
    """Surface a status message in the floating banner.

    The input frame is forwarded unchanged so the node sits inline.
    ``severity`` chooses INFO (blue) / WARNING (amber) — run
    continues — or ERROR (red), which raises a ``RuntimeError`` and
    aborts the run. ``message`` is a port-style input: type a literal
    or wire any ``STRING`` source in to drive it per frame.
    """

    message = StringParam(
        "",
        placeholder="message shown in the banner",
        description=(
            "Text shown in the floating banner (or carried by "
            "the raised RuntimeError when severity is ERROR). "
            "Wire any STRING source in to drive the message "
            "per frame."
        ),
    )
    # ``constant=True``: the severity is a once-per-node UX choice,
    # not a per-frame value worth driving from upstream — render
    # inline with no socket dot.
    severity = EnumParam(
        NotifySeverity,
        NotifySeverity.INFO,
        constant=True,
        description=(
            "INFO (blue) and WARNING (amber) keep the run going; "
            "ERROR (red) raises a RuntimeError that aborts at "
            "this node."
        ),
    )

    def __init__(self) -> None:
        super().__init__("Notify", section="UI")
        self._add_input(InputPort("image", set(IMAGE_TYPES)))
        self._add_output(OutputPort("image", set(IMAGE_TYPES)))
        self._apply_default_params()

    @override
    def process_impl(self) -> None:
        in_data = self.inputs[0].data
        if self._severity is NotifySeverity.ERROR:
            raise RuntimeError(self._message)
        if self._severity is NotifySeverity.WARNING:
            notifications.warn(self._message)
        else:
            notifications.info(self._message)
        self.outputs[0].send(in_data)

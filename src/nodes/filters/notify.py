from __future__ import annotations

from enum import IntEnum

from typing_extensions import override

from core import notifications
from core.io_data import IMAGE_TYPES, IoDataType
from core.node_base import NodeBase, NodeParam, NodeParamType
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

    Drop the node anywhere on an image edge: the input frame is
    forwarded unchanged on the output (so the node sits inline
    without altering the pipeline) and the configured ``message`` is
    emitted at the chosen ``severity``:

    - ``INFO`` (blue) — neutral status, run continues.
    - ``WARNING`` (amber) — non-fatal issue, run continues.
    - ``ERROR`` (red) — raises a ``RuntimeError``, run aborts at the
      node (matching :class:`ThrowException`'s behaviour).

    The ``message`` is a port-style input: type a literal string into
    the inline editor, or wire any ``STRING`` source into the socket
    to drive the message per frame (e.g. a ``ConstantValue`` carrying
    a status line, or a node that computes the text dynamically).

    Parameters:
      severity -- :class:`NotifySeverity` choice; info / warning / error.
      message  -- Text shown in the banner / exception. Empty messages
                  are forwarded verbatim.
    """

    def __init__(self) -> None:
        super().__init__("Notify", section="UI")
        self._severity: NotifySeverity = NotifySeverity.INFO
        self._message:  str = ""

        self._add_input(InputPort("image", set(IMAGE_TYPES)))
        self._add_input(InputPort(
            "message",
            {IoDataType.STRING},
            optional=True,
            default_value="",
            metadata={
                "default":     "",
                "placeholder": "message shown in the banner",
                "param_type":  NodeParamType.STRING,
                "description": (
                    "Text shown in the floating banner (or carried by "
                    "the raised RuntimeError when severity is ERROR). "
                    "Wire any STRING source in to drive the message "
                    "per frame."
                ),
            },
        ))
        self._add_param(NodeParam(
            "severity",
            NodeParamType.ENUM,
            default=NotifySeverity.INFO,
            metadata={
                "enum": NotifySeverity,
                "description": (
                    "INFO (blue) and WARNING (amber) keep the run going; "
                    "ERROR (red) raises a RuntimeError that aborts at "
                    "this node."
                ),
            },
        ))
        self._add_output(OutputPort("image", set(IMAGE_TYPES)))

        self._apply_default_params()

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def severity(self) -> NotifySeverity:
        return self._severity

    @severity.setter
    def severity(self, value: int | NotifySeverity) -> None:
        try:
            self._severity = NotifySeverity(value)
        except ValueError as exc:
            raise ValueError(
                f"severity must be one of {[s.value for s in NotifySeverity]} "
                f"(got {value!r})"
            ) from exc

    @property
    def message(self) -> str:
        return self._message

    @message.setter
    def message(self, value: str) -> None:
        self._message = str(value)

    # ── NodeBase interface ─────────────────────────────────────────────────────

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

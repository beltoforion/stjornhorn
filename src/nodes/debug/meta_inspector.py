from __future__ import annotations

from typing import Callable

from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase
from core.port import InputPort, OutputPort


#: Set of payload kinds the inspector accepts on its input. Covers every
#: :class:`IoDataType` so the node can sit inline anywhere in a flow as a
#: debug probe without the user having to pick a "compatible" connection.
_ALL_TYPES: frozenset[IoDataType] = frozenset(IoDataType)


class MetaInspector(NodeBase):
    """Pass-through node that surfaces each frame's :class:`IoMeta` to a
    preview widget.

    Accepts every payload kind so the inspector can sit inline anywhere
    in a streaming flow as a debug probe — image, scalar, dataset,
    matrix, all flow through unchanged. Each frame's meta dict is
    handed to the UI via :meth:`set_frame_callback`; the preview
    widget renders the field-by-field text on the main thread.

    The node itself is Qt-free; the worker-thread → main-thread hop
    is the preview widget's responsibility (queued signal).
    """

    HEADER_ICON = "info"

    def __init__(self) -> None:
        super().__init__("Meta Inspector", section="Debug")
        self._frame_callback: Callable[[IoData], None] | None = None
        self._add_input(InputPort("data", set(_ALL_TYPES)))
        self._add_output(OutputPort("data", set(_ALL_TYPES)))

    # ── UI integration ─────────────────────────────────────────────────────────

    def set_frame_callback(
        self, callback: Callable[[IoData], None] | None,
    ) -> None:
        """Attach (or clear) a callback invoked with each new IoData.

        The full envelope is handed over so the preview can render
        meta fields, payload kind, and payload shape side by side.
        Fires on whichever thread :meth:`process_impl` runs on; the
        UI widget is responsible for marshalling back to the main
        thread.
        """
        self._frame_callback = callback

    # ── NodeBase interface ─────────────────────────────────────────────────────

    @override
    def process_impl(self) -> None:
        in_data = self.inputs[0].data
        if self._frame_callback is not None:
            self._frame_callback(in_data)
        self.outputs[0].send(in_data)

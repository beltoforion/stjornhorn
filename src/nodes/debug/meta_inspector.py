from __future__ import annotations

from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import Command, NodeBase
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
    is the preview widget's responsibility (queued signal). The
    "copy meta" :class:`Command` declared in ``_header_items`` is
    also Qt-free at the node level: the handler returns the text,
    and :class:`ui.node_item.NodeItem` performs the clipboard write.
    """

    HEADER_ICON = "info"
    # The inspector's preview *is* the meta dump, so the auto-injected
    # info :class:`Toggle` would be redundant — opt out so the title
    # bar stays uncluttered.
    HAS_INFO_TOGGLE: bool = False

    def __init__(self) -> None:
        super().__init__("Meta Inspector", section="Debug")
        self._add_input(InputPort("data", set(_ALL_TYPES)))
        self._add_output(OutputPort("data", set(_ALL_TYPES)))
        self._header_items.append(Command(
            glyph="content_copy",
            tooltip="Copy meta to clipboard",
            handler=self._copy_meta_text,
        ))

    # ── UI integration ─────────────────────────────────────────────────────────

    def _copy_meta_text(self) -> str | None:
        """Return the formatted meta text for the most recent frame, or
        ``None`` if no frame has been seen yet (so the header button
        is a no-op before the flow runs)."""
        data = self._last_inputs[0] if self._last_inputs else None
        if data is None:
            return None
        return format_meta(data)

    # ── NodeBase interface ─────────────────────────────────────────────────────

    @override
    def process_impl(self) -> None:
        in_data = self.inputs[0].data
        self.outputs[0].send(in_data)


def format_meta(data: IoData) -> str:
    """Render an :class:`IoData` envelope's meta + payload summary as
    readable text for the inspector preview and copy-to-clipboard.

    The meta bag is open-ended; every key is rendered in sorted order
    so the inspector reflects whatever the upstream nodes stamped,
    without hard-coding which keys exist.
    """
    shape = getattr(data.payload, "shape", None)
    payload_line = (
        f"payload: {data.type.name} shape={shape}"
        if shape is not None
        else f"payload: {data.type.name} value={data.payload!r}"
    )
    if not data.meta:
        return f"meta: (empty)\n{payload_line}"

    # Right-pad keys to a common width so values line up vertically.
    key_width = max(len(k) for k in data.meta)
    meta_lines = [
        f"{key.ljust(key_width)}  {data.meta[key]}"
        for key in sorted(data.meta)
    ]
    return "\n".join(meta_lines + [payload_line])

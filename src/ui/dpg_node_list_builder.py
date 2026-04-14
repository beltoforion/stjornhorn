from __future__ import annotations

import dearpygui.dearpygui as dpg

from core.node_registry import NodeEntry, NodeRegistry
from ui._types import DpgTag


class DpgNodeListBuilder:
    """Drag-source list widget enumerating registered nodes by category.

    The widget owns its container, search input and per-entry drag payloads.
    Consumers drop nodes onto a canvas by setting
    ``payload_type=DpgNodeListBuilder.PAYLOAD_TYPE`` on their drop target; the
    ``drag_data`` delivered to the drop callback is the :class:`NodeEntry`.

    Must be instantiated inside an active DPG container context.
    """

    PAYLOAD_TYPE: str = "NODE_LIST"

    _CATEGORIES: tuple[str, ...] = ("Sources", "Filters", "Sinks")

    def __init__(self, registry: NodeRegistry, *, width: int = 200) -> None:
        self._items: list[tuple[DpgTag, str]] = []

        with dpg.child_window(width=width, height=-1, border=True):
            dpg.add_input_text(hint="Search…", width=-1, callback=self._on_search)
            dpg.add_separator()

            categorized = registry.nodes_by_category()
            for category in self._CATEGORIES:
                entries = categorized.get(category, [])
                with dpg.collapsing_header(label=f"{category}  ({len(entries)})", default_open=True):
                    if not entries:
                        dpg.add_text("(none)", color=(120, 120, 120, 255))
                    for entry in entries:
                        self._add_draggable_entry(entry)

    # ── Internals ──────────────────────────────────────────────────────────────

    def _add_draggable_entry(self, entry: NodeEntry) -> None:
        tag = dpg.generate_uuid()
        dpg.add_button(label=entry.display_name, tag=tag, width=-1)
        with dpg.drag_payload(parent=tag, drag_data=entry, payload_type=self.PAYLOAD_TYPE):
            dpg.add_text(f"+ {entry.display_name}")
        self._items.append((tag, entry.display_name.lower()))

    def _on_search(self, sender: DpgTag, value: str) -> None:
        query = value.strip().lower()
        for tag, text in self._items:
            dpg.configure_item(tag, show=(not query or query in text))

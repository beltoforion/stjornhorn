from __future__ import annotations

import json
from typing import TYPE_CHECKING

from PySide6.QtCore import QMimeData, QSize, Qt
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (
    QAbstractItemView,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from core.node_registry import NodeRegistry

#: Custom MIME type carrying a JSON-encoded NodeEntry descriptor.
NODE_LIST_MIME_TYPE: str = "application/x-image-inquest-node"


class PaletteWidget(QWidget):
    """Palette listing every registered node by category.

    Each entry is a :class:`QListWidgetItem` that emits a drag with the
    :data:`NODE_LIST_MIME_TYPE` MIME type carrying a JSON descriptor of
    the node (module, class_name, display_name, category). The flow
    canvas reads that payload on drop and instantiates the node.

    A search box filters the list live; matching falls back to case-
    insensitive ``in`` on display names.
    """

    _CATEGORIES: tuple[str, ...] = ("Sources", "Filters", "Sinks")

    def __init__(self, registry: NodeRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search…")
        self._search.textChanged.connect(self._on_search)
        layout.addWidget(self._search)

        self._list = _DraggableList()
        layout.addWidget(self._list, 1)

        self._populate(registry)

    # ── Internals ──────────────────────────────────────────────────────────────

    def _populate(self, registry: NodeRegistry) -> None:
        categorized = registry.nodes_by_category()
        for category in self._CATEGORIES:
            entries = categorized.get(category, [])
            # Category header is a non-selectable, non-draggable item.
            header = QListWidgetItem(f"{category}  ({len(entries)})")
            font = header.font()
            font.setBold(True)
            header.setFont(font)
            header.setFlags(Qt.ItemFlag.NoItemFlags)
            header.setData(Qt.ItemDataRole.UserRole, None)
            self._list.addItem(header)

            if not entries:
                placeholder = QListWidgetItem("    (none)")
                placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
                placeholder.setForeground(Qt.GlobalColor.gray)
                self._list.addItem(placeholder)
                continue

            for entry in entries:
                item = QListWidgetItem(f"  {entry.display_name}")
                payload = json.dumps({
                    "module":       entry.module,
                    "class_name":   entry.class_name,
                    "display_name": entry.display_name,
                    "category":     entry.category,
                })
                item.setData(Qt.ItemDataRole.UserRole, payload)
                item.setToolTip(f"{entry.module}.{entry.class_name}")
                self._list.addItem(item)

    def _on_search(self, text: str) -> None:
        query = text.strip().lower()
        for i in range(self._list.count()):
            item = self._list.item(i)
            # Never hide category headers — context matters.
            if item.flags() == Qt.ItemFlag.NoItemFlags:
                item.setHidden(False)
                continue
            item.setHidden(bool(query) and query not in item.text().lower())


class _DraggableList(QListWidget):
    """QListWidget that emits a NodeEntry drag when an item is dragged."""

    def __init__(self) -> None:
        super().__init__()
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setIconSize(QSize(0, 0))

    def startDrag(self, supported_actions) -> None:  # type: ignore[override]
        item = self.currentItem()
        if item is None:
            return
        payload = item.data(Qt.ItemDataRole.UserRole)
        if not payload:
            return

        mime = QMimeData()
        mime.setData(NODE_LIST_MIME_TYPE, payload.encode("utf-8"))
        mime.setText(item.text().strip())   # so plain drop targets still get something

        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)

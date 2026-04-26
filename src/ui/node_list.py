from __future__ import annotations

import json
from typing import TYPE_CHECKING

from PySide6.QtCore import QMimeData, QSize, Qt
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.icons import material_icon

if TYPE_CHECKING:
    from core.node_registry import NodeRegistry

#: Custom MIME type carrying a JSON-encoded NodeEntry descriptor.
NODE_LIST_MIME_TYPE: str = "application/x-image-inquest-node"

#: Canonical display order for the well-known palette sections. Any
#: section not listed here (e.g. defined by a user-provided plugin node)
#: is appended after these in the order the registry reports them.
_SECTION_ORDER: tuple[str, ...] = (
    "Sources",
    "Sinks",
    "Color Spaces",
    "Transform",
    "Processing",
    "Composit",
)


class NodeList(QWidget):
    """Palette listing every registered node grouped by the ``section``
    string each node declares in its constructor.

    The widget is a :class:`QTreeWidget` where each section is a
    collapsible top-level item and its nodes are children. A toolbar
    above the tree exposes "expand all" / "collapse all" affordances and
    a live search box that hides non-matching leaves while always
    keeping the section headers visible.

    Each leaf is a :class:`QTreeWidgetItem` that emits a drag with the
    :data:`NODE_LIST_MIME_TYPE` MIME type carrying a JSON descriptor of
    the node (module, class_name, display_name, category, section). The
    flow canvas reads that payload on drop and instantiates the node.
    """

    def __init__(self, registry: NodeRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Toolbar: expand-all / collapse-all + search. Buttons are kept
        # narrow (icon-only) so the search field gets the rest of the row.
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.setSpacing(4)

        self._expand_btn = QToolButton()
        self._expand_btn.setIcon(material_icon("unfold_more"))
        self._expand_btn.setToolTip("Expand all groups")
        self._expand_btn.setAutoRaise(True)
        self._expand_btn.clicked.connect(self._expand_all)
        toolbar.addWidget(self._expand_btn)

        self._collapse_btn = QToolButton()
        self._collapse_btn.setIcon(material_icon("unfold_less"))
        self._collapse_btn.setToolTip("Collapse all groups")
        self._collapse_btn.setAutoRaise(True)
        self._collapse_btn.clicked.connect(self._collapse_all)
        toolbar.addWidget(self._collapse_btn)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search…")
        self._search.textChanged.connect(self._on_search)
        toolbar.addWidget(self._search, 1)

        layout.addLayout(toolbar)

        self._tree = _DraggableTree()
        layout.addWidget(self._tree, 1)

        self._populate(registry)
        self._tree.expandAll()

    # ── Internals ──────────────────────────────────────────────────────────────

    def _populate(self, registry: NodeRegistry) -> None:
        grouped = registry.nodes_by_section()
        # Render well-known sections first in canonical order, then any
        # novel sections (e.g. from user plugins) in registry order.
        seen: set[str] = set()
        ordered_sections: list[str] = []
        for name in _SECTION_ORDER:
            if name in grouped:
                ordered_sections.append(name)
                seen.add(name)
        for name in grouped.keys():
            if name not in seen:
                ordered_sections.append(name)
                seen.add(name)

        for section in ordered_sections:
            entries = grouped.get(section, [])
            header = QTreeWidgetItem([f"{section}  ({len(entries)})"])
            font = header.font(0)
            font.setBold(True)
            header.setFont(0, font)
            # Section rows are organisational only — no drag payload, no
            # selection. Keeping them enabled lets the user click the
            # row (not just the disclosure triangle) to toggle expansion.
            header.setFlags(Qt.ItemFlag.ItemIsEnabled)
            header.setData(0, Qt.ItemDataRole.UserRole, None)
            self._tree.addTopLevelItem(header)

            if not entries:
                placeholder = QTreeWidgetItem(["(none)"])
                placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
                placeholder.setForeground(0, Qt.GlobalColor.gray)
                header.addChild(placeholder)
                continue

            for entry in entries:
                item = QTreeWidgetItem([entry.display_name])
                payload = json.dumps({
                    "module":       entry.module,
                    "class_name":   entry.class_name,
                    "display_name": entry.display_name,
                    "category":     entry.category,
                    "section":      entry.section,
                })
                item.setData(0, Qt.ItemDataRole.UserRole, payload)
                item.setToolTip(0, f"{entry.module}.{entry.class_name}")
                header.addChild(item)

    def _on_search(self, text: str) -> None:
        query = text.strip().lower()
        for i in range(self._tree.topLevelItemCount()):
            section = self._tree.topLevelItem(i)
            any_visible = False
            for j in range(section.childCount()):
                child = section.child(j)
                payload = child.data(0, Qt.ItemDataRole.UserRole)
                if payload is None:
                    # Placeholder "(none)" row — hide it during a search
                    # so empty sections don't get a misleading match.
                    child.setHidden(bool(query))
                    continue
                matches = (not query) or (query in child.text(0).lower())
                child.setHidden(not matches)
                any_visible = any_visible or matches
            # Section headers stay visible (context matters), but expand
            # automatically while a search is active so matches are not
            # hidden behind a collapsed group.
            section.setHidden(False)
            if query:
                section.setExpanded(any_visible)

    def _expand_all(self) -> None:
        self._tree.expandAll()

    def _collapse_all(self) -> None:
        self._tree.collapseAll()


class _DraggableTree(QTreeWidget):
    """QTreeWidget that emits a NodeEntry drag when a leaf is dragged."""

    def __init__(self) -> None:
        super().__init__()
        self.setHeaderHidden(True)
        self.setColumnCount(1)
        self.setRootIsDecorated(True)
        self.setIndentation(14)
        self.setUniformRowHeights(True)
        self.setExpandsOnDoubleClick(True)
        self.setItemsExpandable(True)
        self.setAnimated(False)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setIconSize(QSize(0, 0))
        # Single visible column should fill the viewport.
        self.header().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

    def startDrag(self, supported_actions) -> None:  # type: ignore[override]
        item = self.currentItem()
        if item is None:
            return
        payload = item.data(0, Qt.ItemDataRole.UserRole)
        if not payload:
            return

        mime = QMimeData()
        mime.setData(NODE_LIST_MIME_TYPE, payload.encode("utf-8"))
        mime.setText(item.text(0).strip())   # so plain drop targets still get something

        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)

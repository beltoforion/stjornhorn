"""Widget-level tests for :class:`ui.node_doc_panel.NodeDocPanel` and
its selection wiring on :class:`ui.node_list.NodeList`.

These exercise the Qt-side glue that the pure-function renderer tests
deliberately avoid: that the panel actually feeds its browser through
``render_node_doc`` for a class, that the empty state shows when
nothing is selected, and that ``NodeList.entry_selected`` fires with
the right payload.
"""
from __future__ import annotations

import os
import sys

# Offscreen platform plugin avoids the libEGL / X-server requirement;
# must be set before any PySide6 import.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QTreeWidgetItem

from constants import BUILTIN_NODES_DIR
from core.node_registry import NodeRegistry
from nodes.filters.gaussian_blur import GaussianBlur
from ui.node_doc_panel import NodeDocPanel
from ui.node_list import NodeList


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture(scope="module")
def registry() -> NodeRegistry:
    reg = NodeRegistry()
    errors = reg.scan_builtin(BUILTIN_NODES_DIR)
    assert not errors, errors
    return reg


def test_panel_starts_in_empty_state(qapp: QApplication) -> None:
    panel = NodeDocPanel()
    text = panel._browser.toMarkdown()
    assert "Select a node" in text


def test_show_class_renders_node_documentation(qapp: QApplication) -> None:
    """Asking the panel to show a real class produces a Markdown
    document containing the class's display name and its inputs —
    proof that the browser is actually fed through
    :func:`render_node_doc`."""
    panel = NodeDocPanel()
    panel.show_class(GaussianBlur)
    text = panel._browser.toMarkdown()
    assert "Gaussian Blur" in text
    assert "ksize" in text


def test_clear_returns_to_empty_state(qapp: QApplication) -> None:
    panel = NodeDocPanel()
    panel.show_class(GaussianBlur)
    panel.clear()
    text = panel._browser.toMarkdown()
    assert "Select a node" in text


def test_show_class_swallows_introspection_failures(qapp: QApplication) -> None:
    """A class whose constructor raises must not crash the panel — the
    fallback message takes over instead."""
    class BrokenNode:
        def __init__(self) -> None:
            raise RuntimeError("unwirable")

    panel = NodeDocPanel()
    panel.show_class(BrokenNode)  # type: ignore[arg-type]
    text = panel._browser.toMarkdown()
    assert "Could not introspect" in text
    assert "BrokenNode" in text


def test_show_entry_resolves_class_via_registry(
    qapp: QApplication, registry: NodeRegistry,
) -> None:
    """A palette ``NodeEntry`` carries ``module`` + ``class_name``;
    :meth:`NodeDocPanel.show_entry` imports and forwards to
    :meth:`show_class`."""
    panel = NodeDocPanel()
    entry = registry.nodes["GaussianBlur"]
    panel.show_entry(entry)
    text = panel._browser.toMarkdown()
    assert "Gaussian Blur" in text


def test_node_list_emits_entry_selected_for_leaf_rows(
    qapp: QApplication, registry: NodeRegistry,
) -> None:
    """Clicking a leaf in the palette emits ``entry_selected`` with the
    matched :class:`NodeEntry`; this is the signal the host page wires
    into the panel."""
    node_list = NodeList(registry)
    received: list[object] = []
    node_list.entry_selected.connect(received.append)

    leaf = _find_leaf(node_list, "GaussianBlur")
    node_list._tree.setCurrentItem(leaf)

    assert received, "expected entry_selected to fire on leaf selection"
    assert received[-1] is not None
    assert received[-1].class_name == "GaussianBlur"


def test_node_list_emits_none_for_section_headers(
    qapp: QApplication, registry: NodeRegistry,
) -> None:
    """Section headers and the ``(none)`` placeholder emit ``None``,
    so the panel falls back to its empty state instead of trying to
    render a non-class."""
    node_list = NodeList(registry)
    received: list[object] = []
    node_list.entry_selected.connect(received.append)

    # Find the first section header (a top-level item with no JSON payload).
    header = node_list._tree.topLevelItem(0)
    node_list._tree.setCurrentItem(header)

    assert received and received[-1] is None


def _find_leaf(node_list: NodeList, class_name: str) -> QTreeWidgetItem:
    """Walk the palette tree and return the leaf for *class_name*."""
    import json
    tree = node_list._tree
    for i in range(tree.topLevelItemCount()):
        section = tree.topLevelItem(i)
        for j in range(section.childCount()):
            child = section.child(j)
            payload = child.data(0, 256)  # Qt.ItemDataRole.UserRole == 256
            if not payload:
                continue
            if json.loads(payload).get("class_name") == class_name:
                return child
    pytest.fail(f"leaf {class_name!r} not found in palette")

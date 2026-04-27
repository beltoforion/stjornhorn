"""Widget-level tests for :class:`ui.node_doc_panel.NodeDocPanel` and
its selection wiring on :class:`ui.node_list.NodeList`.

These exercise the Qt-side glue that the pure-function renderer tests
deliberately avoid: that the panel actually feeds its summary label
and details browser through the renderers, that the disclosure
toggle collapses / expands the body the way the user expects, and
that ``NodeList.entry_selected`` fires with the right payload.
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


# ── Empty state ────────────────────────────────────────────────────────────────

def test_panel_starts_in_empty_state(qapp: QApplication) -> None:
    panel = NodeDocPanel()
    assert "Select a node" in panel._summary.text()
    # No node loaded yet → nothing to expand → toggle hidden.
    assert panel._toggle.isHidden()
    assert panel._details.isHidden()


# ── show_class ─────────────────────────────────────────────────────────────────

def test_show_class_renders_summary_and_keeps_details_collapsed(
    qapp: QApplication,
) -> None:
    """Showing a class fills the always-visible summary head, but
    the details body stays collapsed by default — the user must
    click the disclosure to see the full docs."""
    panel = NodeDocPanel()
    panel.show_class(GaussianBlur)
    assert "Gaussian Blur" in panel._summary.text()
    assert not panel._toggle.isHidden(), (
        "GaussianBlur has ports + params, so the disclosure must show"
    )
    assert panel._details.isHidden(), (
        "details body must be collapsed by default"
    )
    # The details HTML is loaded even while hidden — toggling on
    # later must not require a re-render.
    assert "ksize" in panel._details.toMarkdown()


def test_clicking_toggle_expands_details(qapp: QApplication) -> None:
    panel = NodeDocPanel()
    panel.show_class(GaussianBlur)
    panel._toggle.setChecked(True)
    assert not panel._details.isHidden()


def test_clicking_toggle_again_collapses_details(qapp: QApplication) -> None:
    panel = NodeDocPanel()
    panel.show_class(GaussianBlur)
    panel._toggle.setChecked(True)
    panel._toggle.setChecked(False)
    assert panel._details.isHidden()


def test_toggle_state_survives_selection_change(qapp: QApplication) -> None:
    """A user reading docs for one node and clicking another should
    not have to re-open the disclosure — the open state carries over
    so the next class lands already-expanded."""
    from nodes.filters.resize import Resize
    panel = NodeDocPanel()
    panel.show_class(GaussianBlur)
    panel._toggle.setChecked(True)
    panel.show_class(Resize)
    assert panel._toggle.isChecked()
    assert not panel._details.isHidden()
    assert "Resize" in panel._summary.text()


def test_clear_returns_to_empty_state(qapp: QApplication) -> None:
    panel = NodeDocPanel()
    panel.show_class(GaussianBlur)
    panel._toggle.setChecked(True)
    panel.clear()
    assert "Select a node" in panel._summary.text()
    assert panel._toggle.isHidden()
    assert panel._details.isHidden()


def test_show_class_swallows_introspection_failures(qapp: QApplication) -> None:
    """A class whose constructor raises must not crash the panel —
    the fallback message takes over the summary head and the
    disclosure is hidden."""
    class BrokenNode:
        def __init__(self) -> None:
            raise RuntimeError("unwirable")

    panel = NodeDocPanel()
    panel.show_class(BrokenNode)  # type: ignore[arg-type]
    assert "Could not introspect" in panel._summary.text()
    assert "BrokenNode" in panel._summary.text()
    assert panel._toggle.isHidden()


# ── show_entry (palette path) ──────────────────────────────────────────────────

def test_show_entry_resolves_class_via_registry(
    qapp: QApplication, registry: NodeRegistry,
) -> None:
    """A palette ``NodeEntry`` carries ``module`` + ``class_name``;
    :meth:`NodeDocPanel.show_entry` imports and forwards to
    :meth:`show_class`."""
    panel = NodeDocPanel()
    entry = registry.nodes["GaussianBlur"]
    panel.show_entry(entry)
    assert "Gaussian Blur" in panel._summary.text()


# ── NodeList selection signal ──────────────────────────────────────────────────

def test_node_list_emits_entry_selected_for_leaf_rows(
    qapp: QApplication, registry: NodeRegistry,
) -> None:
    """Clicking a leaf in the palette emits ``entry_selected`` with
    the matched :class:`NodeEntry`; this is the signal the host page
    wires into the panel."""
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

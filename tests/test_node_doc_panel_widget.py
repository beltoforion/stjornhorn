"""Widget-level tests for :class:`ui.node_doc_panel.NodeDocPanel` and
its selection wiring on :class:`ui.node_list.NodeList`.

These exercise the Qt-side glue that the pure-function renderer
tests deliberately avoid: that the panel actually feeds its body
browser through :func:`render_node_html`, that the empty / error
states render cleanly, and that ``NodeList.entry_selected`` fires
with the right payload.
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
    assert "Select a node" in panel._body.toHtml()


# ── show_class ─────────────────────────────────────────────────────────────────

def test_show_class_renders_full_doc_in_one_body(qapp: QApplication) -> None:
    """Showing a class fills the body with the full doc — display
    name, description, Inputs, Outputs and Parameters all in one
    place with nothing behind a disclosure."""
    panel = NodeDocPanel()
    panel.show_class(GaussianBlur)
    html = panel._body.toHtml()
    assert "Gaussian Blur" in html
    # GaussianBlur's editable inputs (ksize, sigma) appear in the
    # Inputs section; with the toggle gone they must be visible
    # immediately, no click needed.
    assert "ksize" in html
    assert "sigma" in html


def test_show_class_renders_sections_in_canonical_order(
    qapp: QApplication,
) -> None:
    """Inputs → Outputs → Parameters. Use a node that has constant
    params so all three sections are present."""
    from nodes.sources.gradient_source import GradientSource
    panel = NodeDocPanel()
    panel.show_class(GradientSource)
    html = panel._body.toHtml()
    outputs_at = html.index("Outputs")
    params_at = html.index("Parameters")
    assert outputs_at < params_at


def test_show_class_swallows_introspection_failures(
    qapp: QApplication,
) -> None:
    """A class whose constructor raises must not crash the panel —
    the fallback message takes over the body instead."""
    class BrokenNode:
        def __init__(self) -> None:
            raise RuntimeError("unwirable")

    panel = NodeDocPanel()
    panel.show_class(BrokenNode)  # type: ignore[arg-type]
    html = panel._body.toHtml()
    assert "Could not introspect" in html
    assert "BrokenNode" in html


def test_clear_returns_to_empty_state(qapp: QApplication) -> None:
    panel = NodeDocPanel()
    panel.show_class(GaussianBlur)
    panel.clear()
    assert "Select a node" in panel._body.toHtml()


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
    assert "Gaussian Blur" in panel._body.toHtml()


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


# ── Size negotiation (issue #233) ────────────────────────────────────────────

from core.node_base import NodeBase


class _LongDocNode(NodeBase):
    __doc__ = "Short summary line.\n\n" + "\n\n".join(
        f"Paragraph {i}: " + ("filler text " * 40) for i in range(1, 11)
    )

    def __init__(self) -> None:
        super().__init__("Long Doc Test", section="Test")

    def process_impl(self) -> None:  # pragma: no cover - never executed
        pass


def test_size_hint_constant_across_show_class(qapp: QApplication) -> None:
    """Selecting different classes must not change the panel's reported
    size — that's what kept the dock from auto-resizing in #233."""
    panel = NodeDocPanel()
    initial = panel.sizeHint()
    initial_min = panel.minimumSizeHint()

    panel.show_class(GaussianBlur)
    assert panel.sizeHint() == initial
    assert panel.minimumSizeHint() == initial_min

    panel.show_class(_LongDocNode)
    assert panel.sizeHint() == initial
    assert panel.minimumSizeHint() == initial_min


def test_minimum_size_hint_below_default(qapp: QApplication) -> None:
    """The minimum size must be smaller than the default hint so the
    user can shrink the dock without the panel pushing back."""
    panel = NodeDocPanel()
    assert panel.minimumSizeHint().height() < panel.sizeHint().height()
    assert panel.minimumSizeHint().width() < panel.sizeHint().width()

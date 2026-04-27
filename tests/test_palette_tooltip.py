"""Verify that the node palette's hover tooltip surfaces the class
docstring instead of the dotted import path.

Pre-fix behaviour: hovering ``Resize`` in the palette showed
``nodes.filters.resize.Resize`` — accurate but useless to a user.
Post-fix: the first paragraph of the class docstring is shown, with
the dotted path as a fallback only when the class is undocumented (so
the sweep tracked under issue #187 has a visible reason to happen).
"""
from __future__ import annotations

from core.node_registry import NodeEntry
from ui.node_list import _palette_tooltip


def _entry(docstring: str = "") -> NodeEntry:
    return NodeEntry(
        class_name="Resize",
        display_name="Resize",
        category="Filters",
        section="Transform",
        module="nodes.filters.resize",
        docstring=docstring,
    )


def test_tooltip_uses_first_paragraph_of_docstring() -> None:
    """A multi-paragraph docstring is truncated to the first paragraph
    so the popup stays digestible on hover."""
    entry = _entry(
        "Resize an image to an explicit (width, height).\n\n"
        "Parameters:\n"
        "  width  -- target width.\n"
        "  height -- target height."
    )
    assert _palette_tooltip(entry) == (
        "Resize an image to an explicit (width, height)."
    )


def test_tooltip_falls_back_to_dotted_path_when_undocumented() -> None:
    """A node without a docstring keeps the legacy import-path
    tooltip — uninspiring, but at least it identifies the node and
    makes the missing-doc case visible during the sweep."""
    entry = _entry(docstring="")
    assert _palette_tooltip(entry) == "nodes.filters.resize.Resize"


def test_tooltip_truncates_long_first_paragraph() -> None:
    """A pathologically long single paragraph is capped with an
    ellipsis so the tooltip never grows unbounded."""
    long_text = "This is a very long description. " * 30
    entry = _entry(long_text)
    out = _palette_tooltip(entry)
    assert len(out) <= 400
    assert out.endswith("…")


def test_registry_populates_docstring_from_real_nodes() -> None:
    """End-to-end: the AST scanner actually fills NodeEntry.docstring,
    so the tooltip helper has something to render in production."""
    from constants import BUILTIN_NODES_DIR
    from core.node_registry import NodeRegistry

    registry = NodeRegistry()
    registry.scan_builtin(BUILTIN_NODES_DIR)
    resize = registry.nodes.get("Resize")
    assert resize is not None, "Resize should be discoverable in the builtin scan"
    assert resize.docstring, (
        "Resize ships with a class docstring; the AST scanner must "
        "expose it on NodeEntry so the palette tooltip can render it."
    )
    tooltip = _palette_tooltip(resize)
    assert "nodes.filters.resize.Resize" not in tooltip, (
        "tooltip regressed to the dotted-path fallback even though the "
        "class has a docstring"
    )

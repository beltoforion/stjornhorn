"""Documentation panel that mirrors the currently selected node.

A dockable widget that consumes :func:`core.node_doc.describe_node` and
renders the result as Markdown. The panel updates from two selection
sources:

* the :class:`~ui.node_list.NodeList` palette on the left — clicking
  an entry shows the docs for that class.
* the :class:`~ui.flow_scene.FlowScene` canvas — clicking a node on
  the graph shows the docs for the underlying class.

Lives in its own dock so the user can hide / float / re-arrange it
through the existing dock-layout machinery
(:mod:`ui.dock_layout`). Empty state shows a one-line hint instead
of a blank panel — a missing tooltip equivalent. Issue: #187
"""
from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from core.node_doc import describe_node

if TYPE_CHECKING:
    from core.node_base import NodeBase
    from core.node_registry import NodeEntry


_EMPTY_STATE_MARKDOWN: str = (
    "_Select a node in the palette or on the canvas to see its "
    "documentation here._"
)


def _render_type_list(types: list[str]) -> str:
    """Format a list of :class:`IoDataType` names for inline display."""
    if not types:
        return "_(none)_"
    return " | ".join(f"`{t}`" for t in types)


def _render_default(value: object) -> str:
    """Format a default value for inline display.

    Strings are quoted; everything else is repr'd. Keeps long paths
    readable and unambiguous about whether a value is text or numeric.
    """
    if isinstance(value, str):
        return f"`'{value}'`"
    return f"`{value!r}`"


def _render_enum_mapping(enum: dict) -> str:
    """Format an ``enum`` metadata mapping (already normalised to
    ``dict[int, str]`` by :func:`describe_node`) as a comma-separated
    list of ``int=NAME`` pairs."""
    return ", ".join(f"{k}={v}" for k, v in sorted(enum.items()))


def _render_param_extras(p: dict) -> list[str]:
    """Pull the small grab-bag of non-description metadata into a
    bullet's trailing ``…`` suffix line — kept short so the panel
    stays readable when many params line up."""
    extras: list[str] = []
    if "default" in p:
        extras.append(f"default {_render_default(p['default'])}")
    if "min" in p:
        extras.append(f"min `{p['min']}`")
    if "max" in p:
        extras.append(f"max `{p['max']}`")
    if "step" in p:
        extras.append(f"step `{p['step']}`")
    if "unit" in p:
        extras.append(f"unit `{p['unit']}`")
    if "enum" in p:
        extras.append(_render_enum_mapping(p["enum"]))
    if "filter" in p:
        extras.append(f"filter `{p['filter']}`")
    return extras


def _render_input_bullet(port: dict) -> str:
    """Render one input port as a Markdown bullet.

    Two variants: image-flow ports (no ``param_type``) get the simple
    ``name — TYPES (required|optional)`` shape; param-style ports get
    the same plus a parenthetical type tag, the description (if any)
    and a metadata-extras suffix line.
    """
    name = port["name"]
    types = _render_type_list(port["accepted_types"])
    required = "" if port["optional"] else " *(required)*"

    if "param_type" not in port:
        return f"- **{name}** — {types}{required}"

    pt = port["param_type"]
    description = port.get("description", "")
    head = f"- **{name}** *(`{pt}`)* — {types}{required}"
    if description:
        head += f"  \n  {description}"
    extras = _render_param_extras(port)
    if extras:
        head += f"  \n  _{' · '.join(extras)}_"
    return head


def _render_param_bullet(param: dict) -> str:
    """Render one constant :class:`NodeParam` as a Markdown bullet."""
    name = param["name"]
    pt = param.get("param_type", "")
    description = param.get("description", "")
    head = f"- **{name}** *(`{pt}`)*"
    if description:
        head += f" — {description}"
    extras = _render_param_extras(param)
    if extras:
        head += f"  \n  _{' · '.join(extras)}_"
    return head


def _render_output_bullet(port: dict) -> str:
    return f"- **{port['name']}** — {_render_type_list(port['emits'])}"


def render_node_doc(desc: dict) -> str:
    """Turn a :func:`core.node_doc.describe_node` dict into Markdown.

    Pure function — no Qt, no class instantiation. Tests against this
    function exercise the entire rendering contract without an
    ``QApplication``.

    Sections appear in the same order whether or not they have
    content, so users can predict where to look. Empty sections
    render as ``_(none)_`` rather than being omitted, because their
    absence carries information ("this node has no parameters" /
    "this is a sink with no outputs").
    """
    lines: list[str] = []
    lines.append(f"# {desc['display_name']}")
    lines.append("")

    section = desc.get("section", "")
    module = desc.get("module", "")
    class_name = desc.get("class_name", "")
    if section or module or class_name:
        bits: list[str] = []
        if section:
            bits.append(f"**Section:** {section}")
        if module and class_name:
            bits.append(f"`{module}.{class_name}`")
        elif class_name:
            bits.append(f"`{class_name}`")
        lines.append(" · ".join(bits))
        lines.append("")

    docstring = desc.get("docstring", "").strip()
    if docstring:
        lines.append(docstring)
        lines.append("")

    inputs = desc.get("inputs", [])
    lines.append("## Inputs")
    if inputs:
        lines.extend(_render_input_bullet(p) for p in inputs)
    else:
        lines.append("_(none)_")
    lines.append("")

    outputs = desc.get("outputs", [])
    lines.append("## Outputs")
    if outputs:
        lines.extend(_render_output_bullet(p) for p in outputs)
    else:
        lines.append("_(none)_")
    lines.append("")

    params = desc.get("params", [])
    lines.append("## Parameters")
    if params:
        lines.extend(_render_param_bullet(p) for p in params)
    else:
        lines.append("_(none)_")
    lines.append("")

    return "\n".join(lines)


class NodeDocPanel(QWidget):
    """Dockable panel that renders the docs of the currently selected node.

    Stateless beyond the most recently displayed class — the host page
    is responsible for wiring selection signals into :meth:`show_class`
    or :meth:`show_entry`.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._browser = QTextBrowser()
        self._browser.setOpenExternalLinks(True)
        # The browser is read-only by default; explicitly disable text
        # interaction beyond mouse selection so a stray double-click on
        # a fragment of the docs doesn't accidentally start text editing
        # via inherited focus styling.
        self._browser.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        layout.addWidget(self._browser)

        self.clear()

    # ── Public slots ───────────────────────────────────────────────────────────

    def show_class(self, cls: type[NodeBase]) -> None:
        """Render documentation for a node *class*.

        The class is instantiated via :func:`describe_node` to read its
        actual port and param shape. Failures fall back to the empty
        state with a brief explanation rather than propagating — the
        panel is supposed to be informative, not a crash surface.
        """
        try:
            desc = describe_node(cls)
        except Exception as exc:  # noqa: BLE001 — we're a UI fallback path
            self._browser.setMarkdown(
                f"_Could not introspect `{cls.__name__}`: {exc}_"
            )
            return
        self._browser.setMarkdown(render_node_doc(desc))

    def show_entry(self, entry: NodeEntry) -> None:
        """Render documentation for a palette :class:`NodeEntry`.

        Imports ``entry.module`` lazily (first selection only — Python
        caches the module thereafter) and resolves the class via
        :func:`getattr`. Same fallback behaviour as :meth:`show_class`
        for failures.
        """
        try:
            module = importlib.import_module(entry.module)
            cls = getattr(module, entry.class_name)
        except Exception as exc:  # noqa: BLE001 — we're a UI fallback path
            self._browser.setMarkdown(
                f"_Could not load `{entry.module}.{entry.class_name}`: {exc}_"
            )
            return
        self.show_class(cls)

    def clear(self) -> None:
        """Show the empty-state hint."""
        self._browser.setMarkdown(_EMPTY_STATE_MARKDOWN)

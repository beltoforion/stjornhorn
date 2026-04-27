"""Documentation panel that mirrors the currently selected node.

A dockable widget that consumes :func:`core.node_doc.describe_node` and
renders the result as compact HTML. The panel updates from two
selection sources:

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

import enum
import html
import importlib
import inspect
import re
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


_EMPTY_STATE_HTML: str = (
    '<p style="color: #9a9a9f; font-style: italic;">'
    "Select a node in the palette or on the canvas to see its "
    "documentation here."
    "</p>"
)

#: Inline stylesheet for the rendered docs. Tuned for a narrow dock
#: (≈ 220 px is the realistic minimum a user wants to give it):
#: small fonts, no fixed-width meta blocks, ``word-break: break-word``
#: on every potentially-long code span so a dotted module path or a
#: long file-dialog filter wraps instead of forcing a horizontal
#: scrollbar. ``<dl>`` instead of bullets so the param name + body
#: lines vertically align with no list-marker gutter. Colour palette
#: mirrors the rest of the editor (panel ``#2f2f33`` / muted text
#: ``#9a9a9f`` / accent ``#f0c83c``).
_PANEL_CSS: str = """
<style>
  body { font-family: 'Segoe UI', sans-serif; font-size: 11px;
         line-height: 1.35; color: #e0e0e0;
         word-wrap: break-word; overflow-wrap: anywhere; }
  h1   { font-size: 14px; margin: 0 0 2px; font-weight: 600;
         color: #f0c83c; }
  .meta { color: #9a9a9f; font-size: 10px; margin: 0 0 6px; }
  .doc  { margin: 0 0 6px; }
  h2   { font-size: 10px; font-weight: 600; text-transform: uppercase;
         letter-spacing: 0.6px; color: #9a9a9f;
         margin: 6px 0 2px; padding-bottom: 1px;
         border-bottom: 1px solid #1a1a1d; }
  dl   { margin: 0 0 4px; }
  dt   { font-weight: 600; margin-top: 3px; }
  dt .type { font-weight: 400; color: #9a9a9f; font-size: 10px;
             margin-left: 3px; }
  dt .req  { color: #e8a86b; font-size: 9px; margin-left: 3px;
             text-transform: uppercase; letter-spacing: 0.4px; }
  dd   { margin: 0 0 0 8px; color: #cfcfd0; }
  dd .extras { color: #9a9a9f; font-size: 10px; }
  code { color: #cfcfd0; word-break: break-all; }
</style>
"""

#: Sphinx cross-reference role pattern. Captures the back-ticked
#: target so the role prefix can be stripped without losing the
#: identifier itself. ``:class:`Resize``` becomes ``Resize``.
#:
#: All six role names that actually appear in the codebase today are
#: handled with one pattern; new roles only need to be added if they
#: contain characters outside ``[a-z]``.
_SPHINX_ROLE_RE: re.Pattern[str] = re.compile(
    r":(?:class|func|meth|attr|data|mod|obj):`([^`]+)`"
)


def _strip_sphinx_roles(text: str) -> str:
    """Replace ``:role:`target``` with just ``target``.

    Source docstrings and metadata descriptions use Sphinx
    cross-reference roles for IDE / autodoc tooling, but the panel
    is for end users — the role prefix is noise. The captured target
    sometimes contains a tilde-prefix
    (``:class:`~ui.flow_scene.FlowScene```) which we shorten to the
    last dotted component the same way Sphinx renders it.
    """
    def _replace(match: re.Match[str]) -> str:
        target = match.group(1)
        if target.startswith("~"):
            target = target[1:].rsplit(".", 1)[-1]
        return target
    return _SPHINX_ROLE_RE.sub(_replace, text)


#: RST inline-code (``` ``foo`` ```) — Sphinx renders this in
#: monospace; the panel mirrors that with ``<code>`` tags so the
#: backtick noise doesn't leak into prose. Single-backtick RST is
#: deliberately ignored because it conflicts with default-value
#: syntax in metadata.
_RST_INLINE_CODE_RE: re.Pattern[str] = re.compile(r"``([^`]+)``")


def _render_prose(text: str) -> str:
    """Turn a docstring / metadata description into HTML body text.

    Steps, in order:
      1. Strip Sphinx role prefixes (``:class:`x``` → ``x``).
      2. Dedent — class docstrings carry their indentation, which
         would survive in HTML as awkward leading spaces in the
         middle of paragraphs.
      3. HTML-escape so user content can't smuggle markup.
      4. Re-introduce the two pieces of light formatting that survive
         escaping: RST inline code (``` ``foo`` ```) becomes
         ``<code>foo</code>``.
    """
    text = _strip_sphinx_roles(text)
    # ``inspect.cleandoc`` is the standard PEP 257 docstring cleanup:
    # it leaves the first line alone, then strips the *minimum* common
    # leading whitespace from the remaining lines. Plain
    # ``textwrap.dedent`` does not work here because a class docstring's
    # first line has zero indentation while the body is indented to
    # match the class — the common prefix is empty and dedent is a
    # no-op. ``cleandoc`` understands that convention.
    text = inspect.cleandoc(text)
    text = html.escape(text)
    text = _RST_INLINE_CODE_RE.sub(r"<code>\1</code>", text)
    return text


def _format_types(types: list[str]) -> str:
    """Render a list of :class:`IoDataType` names as HTML ``<code>``
    elements joined by a thin separator."""
    if not types:
        return '<span style="color: #9a9a9f;">(none)</span>'
    return " | ".join(f"<code>{html.escape(t)}</code>" for t in types)


def _format_default(value: object) -> str:
    """Format a default value for inline display in the extras line.

    Python ``Enum`` members repr as ``<MyEnum.NAME: 0>`` — that string
    leaks the class name and angle brackets into the panel. Render
    just the member name instead, matching the form the param widget
    shows. Numeric and string scalars use the obvious representation.
    """
    if isinstance(value, enum.Enum):
        return html.escape(value.name)
    if isinstance(value, str):
        return html.escape(f"'{value}'")
    return html.escape(repr(value))


def _format_enum_mapping(mapping: dict) -> str:
    """``{0: 'SCALE', 1: 'CROP_OR_FILL'}`` →
    ``0=SCALE, 1=CROP_OR_FILL`` (HTML-escaped)."""
    pairs = (f"{k}={html.escape(str(v))}" for k, v in sorted(mapping.items()))
    return ", ".join(pairs)


def _format_extras(p: dict) -> str:
    """Render the small grab-bag of non-description metadata as one
    semi-colon-separated line. Returns ``""`` when nothing useful is
    present so the caller can drop the line entirely.
    """
    parts: list[str] = []
    if "default" in p:
        parts.append(f"default <code>{_format_default(p['default'])}</code>")
    if "min" in p:
        parts.append(f"min <code>{html.escape(str(p['min']))}</code>")
    if "max" in p:
        parts.append(f"max <code>{html.escape(str(p['max']))}</code>")
    if "step" in p:
        parts.append(f"step <code>{html.escape(str(p['step']))}</code>")
    if "unit" in p:
        parts.append(f"unit <code>{html.escape(str(p['unit']))}</code>")
    if "enum" in p:
        parts.append(_format_enum_mapping(p["enum"]))
    if "filter" in p:
        parts.append(f"filter <code>{html.escape(str(p['filter']))}</code>")
    return " · ".join(parts)


def _render_input(port: dict) -> str:
    """Render one input port as a ``<dt>`` + optional ``<dd>``."""
    name = html.escape(port["name"])
    types = _format_types(port["accepted_types"])
    bits = [f'<span class="type">{types}</span>']
    if not port["optional"]:
        bits.append('<span class="req">required</span>')
    if "param_type" in port:
        bits.append(
            f'<span class="type">'
            f'{html.escape(port["param_type"])}</span>'
        )
    dt = f"<dt>{name} {' '.join(bits)}</dt>"
    dd_lines: list[str] = []
    if port.get("description"):
        dd_lines.append(_render_prose(port["description"]))
    extras = _format_extras(port)
    if extras:
        dd_lines.append(f'<span class="extras">{extras}</span>')
    if not dd_lines:
        return dt
    return f"{dt}<dd>{'<br>'.join(dd_lines)}</dd>"


def _render_param(param: dict) -> str:
    """Render one constant ``NodeParam`` as a ``<dt>`` + optional
    ``<dd>``."""
    name = html.escape(param["name"])
    pt = param.get("param_type", "")
    type_html = f'<span class="type">{html.escape(pt)}</span>' if pt else ""
    dt = f"<dt>{name} {type_html}</dt>"
    dd_lines: list[str] = []
    if param.get("description"):
        dd_lines.append(_render_prose(param["description"]))
    extras = _format_extras(param)
    if extras:
        dd_lines.append(f'<span class="extras">{extras}</span>')
    if not dd_lines:
        return dt
    return f"{dt}<dd>{'<br>'.join(dd_lines)}</dd>"


def _render_output(port: dict) -> str:
    return (
        f'<dt>{html.escape(port["name"])} '
        f'<span class="type">{_format_types(port["emits"])}</span></dt>'
    )


def render_node_doc(desc: dict) -> str:
    """Turn a :func:`core.node_doc.describe_node` dict into HTML.

    Pure function — no Qt, no class instantiation. Tests against this
    function exercise the entire rendering contract without an
    ``QApplication``.

    Empty sections are *omitted* entirely (a sink with no outputs
    just doesn't show an Outputs heading) so the panel stays
    compact. Section boundaries appear in a fixed order whenever
    they appear, so users can predict where to look.
    """
    parts: list[str] = [_PANEL_CSS]

    # H1 carries an HTML ``title`` attribute with the dotted module
    # path so a curious user can hover to see where the class lives,
    # without that long string forcing the dock open. Most QTextBrowser
    # builds honour ``title`` as a tooltip; on those that don't, the
    # information is still accessible via the source.
    display_name = html.escape(desc["display_name"])
    module = desc.get("module") or ""
    class_name = desc.get("class_name") or ""
    full_path = f"{module}.{class_name}" if module and class_name else class_name
    h1_title = f' title="{html.escape(full_path)}"' if full_path else ""
    parts.append(f'<h1{h1_title}>{display_name}</h1>')

    if section := desc.get("section"):
        parts.append(f'<p class="meta">{html.escape(section)}</p>')

    docstring = desc.get("docstring", "").strip()
    if docstring:
        # Convert the docstring's blank-line paragraph breaks into
        # ``<p>`` elements, leave the rest as-is. Preserves intent
        # without paying for a full Markdown / RST renderer.
        paragraphs = [
            f'<p class="doc">{_render_prose(p).strip()}</p>'
            for p in docstring.split("\n\n")
            if p.strip()
        ]
        parts.extend(paragraphs)

    if inputs := desc.get("inputs", []):
        parts.append("<h2>Inputs</h2><dl>")
        parts.extend(_render_input(p) for p in inputs)
        parts.append("</dl>")

    if outputs := desc.get("outputs", []):
        parts.append("<h2>Outputs</h2><dl>")
        parts.extend(_render_output(p) for p in outputs)
        parts.append("</dl>")

    if params := desc.get("params", []):
        parts.append("<h2>Parameters</h2><dl>")
        parts.extend(_render_param(p) for p in params)
        parts.append("</dl>")

    return "".join(parts)


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
            self._browser.setHtml(
                f'<p class="meta">Could not introspect '
                f'<code>{html.escape(cls.__name__)}</code>: '
                f"{html.escape(str(exc))}</p>"
            )
            return
        self._browser.setHtml(render_node_doc(desc))

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
            self._browser.setHtml(
                f'<p class="meta">Could not load '
                f'<code>{html.escape(f"{entry.module}.{entry.class_name}")}</code>: '
                f"{html.escape(str(exc))}</p>"
            )
            return
        self.show_class(cls)

    def clear(self) -> None:
        """Show the empty-state hint."""
        self._browser.setHtml(_EMPTY_STATE_HTML)

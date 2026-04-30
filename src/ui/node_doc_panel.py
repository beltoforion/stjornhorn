"""Documentation panel that mirrors the currently selected node.

A dockable widget that consumes :func:`core.node_doc.describe_node` and
renders the result in a single rich-text body: name + section, the
docstring, then the Inputs / Outputs / Parameters tables.

The panel updates from two selection sources:

* the :class:`~ui.node_list.NodeList` palette on the left — clicking
  an entry shows the docs for that class.
* the :class:`~ui.flow_scene.FlowScene` canvas — clicking a node on
  the graph shows the docs for the underlying class.

Lives in its own dock so the user can hide / float / re-arrange it
through the existing dock-layout machinery
(:mod:`ui.dock_layout`). Empty state shows a one-line hint instead
of a blank panel — a missing-tooltip equivalent. Issues: #187, #233
"""
from __future__ import annotations

import enum
import html
import importlib
import inspect
import re
from typing import TYPE_CHECKING

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QFrame,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from core.node_doc import describe_node

if TYPE_CHECKING:
    from core.node_base import NodeBase
    from core.node_registry import NodeEntry


_EMPTY_STATE_HTML: str = (
    '<span style="color: #9a9a9f; font-style: italic;">'
    "Select a node in the palette or on the canvas to see its "
    "documentation here."
    "</span>"
)

#: CSS for the rendered body. Tuned for a narrow dock (≈ 220 px is
#: the realistic minimum a user wants to give it): small fonts, no
#: fixed-width meta blocks, ``word-break: break-all`` on every
#: potentially-long ``<code>`` span so a dotted module path or a long
#: file-dialog filter wraps instead of forcing a horizontal scrollbar.
#: ``<dl>`` instead of bullets so the param name + body lines vertically
#: align with no list-marker gutter. Colour palette mirrors the rest of
#: the editor (panel ``#2f2f33`` / muted text ``#9a9a9f`` / accent
#: ``#f0c83c``).
_PANEL_CSS: str = """
<style>
  body { font-family: 'Segoe UI', sans-serif; font-size: 11px;
         line-height: 1.35; color: #e0e0e0;
         word-wrap: break-word; overflow-wrap: anywhere; }
  h1   { font-size: 14px; margin: 0 0 2px; font-weight: 600;
         color: #f0c83c; }
  .meta { color: #9a9a9f; font-size: 10px; margin: 0 0 4px; }
  .brief{ margin: 0 0 4px; color: #cfcfd0; }
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
_SPHINX_ROLE_RE: re.Pattern[str] = re.compile(
    r":(?:class|func|meth|attr|data|mod|obj):`([^`]+)`"
)


def _strip_sphinx_roles(text: str) -> str:
    """Replace ``:role:`target``` with just ``target``.

    Source docstrings and metadata descriptions use Sphinx
    cross-reference roles for IDE / autodoc tooling, but the panel
    is for end users — the role prefix is noise. The captured target
    sometimes carries a tilde-prefix
    (``:class:`~ui.flow_scene.FlowScene```) which we shorten to the
    last dotted component the same way Sphinx renders it.
    """
    def _replace(match: re.Match[str]) -> str:
        target = match.group(1)
        if target.startswith("~"):
            target = target[1:].rsplit(".", 1)[-1]
        return target
    return _SPHINX_ROLE_RE.sub(_replace, text)


#: RST inline-code (``` ``foo`` ```) → ``<code>foo</code>``. Single-
#: backtick RST is deliberately ignored because it conflicts with
#: default-value syntax in metadata.
_RST_INLINE_CODE_RE: re.Pattern[str] = re.compile(r"``([^`]+)``")


def _render_prose(text: str) -> str:
    """Turn a docstring / metadata description into HTML body text.

    Strips Sphinx role prefixes, runs PEP-257 ``cleandoc`` to drop
    class-level indentation, HTML-escapes for safety, then re-wraps
    RST inline code in ``<code>`` tags.
    """
    text = _strip_sphinx_roles(text)
    text = inspect.cleandoc(text)
    text = html.escape(text)
    text = _RST_INLINE_CODE_RE.sub(r"<code>\1</code>", text)
    return text


def _docstring_paragraphs(docstring: str) -> list[str]:
    """Split a class docstring into prose-rendered paragraphs.

    The first paragraph is the PEP 257 summary line (rendered with
    ``.brief`` styling); the rest are body paragraphs.
    """
    if not docstring.strip():
        return []
    return [
        _render_prose(p).strip()
        for p in docstring.split("\n\n")
        if p.strip()
    ]


def _format_types(types: list[str]) -> str:
    if not types:
        return '<span style="color: #9a9a9f;">(none)</span>'
    return " | ".join(f"<code>{html.escape(t)}</code>" for t in types)


def _format_default(value: object) -> str:
    """Format a default value for inline display. Enum members render
    as just the member name; other values use ``repr``."""
    if isinstance(value, enum.Enum):
        return html.escape(value.name)
    if isinstance(value, str):
        return html.escape(f"'{value}'")
    return html.escape(repr(value))


def _format_enum_mapping(mapping: dict) -> str:
    pairs = (f"{k}={html.escape(str(v))}" for k, v in sorted(mapping.items()))
    return ", ".join(pairs)


def _format_extras(p: dict) -> str:
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


def render_node_html(desc: dict) -> str:
    """Render the full node documentation as a single HTML body.

    Order, top to bottom: display name + section, the docstring (PEP
    257 summary line styled as ``.brief``, then the rest of the
    paragraphs), Inputs, Outputs, Parameters. Empty sections are
    omitted entirely so a node with no params doesn't show a stray
    Parameters heading.

    Pure function — no Qt — so it's testable without a
    ``QApplication``.
    """
    parts: list[str] = [_PANEL_CSS]

    # H1 carries an HTML ``title`` attribute with the dotted module
    # path so a curious user can hover to see where the class lives.
    display_name = html.escape(desc["display_name"])
    module = desc.get("module") or ""
    class_name = desc.get("class_name") or ""
    full_path = f"{module}.{class_name}" if module and class_name else class_name
    h1_title = f' title="{html.escape(full_path)}"' if full_path else ""
    parts.append(f'<h1{h1_title}>{display_name}</h1>')

    if section := desc.get("section"):
        parts.append(f'<p class="meta">{html.escape(section)}</p>')

    paragraphs = _docstring_paragraphs(desc.get("docstring", ""))
    if paragraphs:
        parts.append(f'<p class="brief">{paragraphs[0]}</p>')
        for p in paragraphs[1:]:
            parts.append(f'<p class="doc">{p}</p>')

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


#: Default size the panel reports to its container. Constant — does **not**
#: depend on the rendered docstring length — so a node with a long docstring
#: never grows the dock and squashes its siblings (e.g. the Node List). When
#: content overflows, the inner ``QTextBrowser`` produces a scroll bar instead.
#: Issue: #233.
_PANEL_DEFAULT_HINT: QSize = QSize(280, 360)

#: Smallest size the panel will accept. Stays well below the default hint
#: so the user can shrink the dock without the panel shouldering it back up.
_PANEL_MIN_HINT: QSize = QSize(180, 80)


class NodeDocPanel(QWidget):
    """Dockable panel that renders the docs of the currently selected node.

    Hosts a single :class:`QTextBrowser` whose body is built by
    :func:`render_node_html`. The browser scrolls internally when
    content overflows, so the panel's reported size stays constant
    across selection changes (issue #233).
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._body = QTextBrowser(self)
        self._body.setOpenExternalLinks(True)
        self._body.setFrameShape(QFrame.Shape.NoFrame)
        self._body.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._body.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._body.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
            | Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        outer.addWidget(self._body)

        self.clear()

    # ── Size negotiation ──────────────────────────────────────────────────────

    def sizeHint(self) -> QSize:  # noqa: D401 — overrides Qt method
        """Constant default size, decoupled from content length.

        Without this, ``QWidget.sizeHint`` is derived from the layout
        and grows with the rendered docstring; the enclosing
        ``QDockWidget`` then resizes itself on every selection change
        and squashes neighbouring docks. Returning a fixed value keeps
        the dock at the user's chosen height; overflow is handled by
        the inner ``QTextBrowser``. Issue: #233.
        """
        return _PANEL_DEFAULT_HINT

    def minimumSizeHint(self) -> QSize:  # noqa: D401 — overrides Qt method
        return _PANEL_MIN_HINT

    # ── Public slots ───────────────────────────────────────────────────────────

    def show_class(self, cls: type[NodeBase]) -> None:
        """Render documentation for a node *class*."""
        try:
            desc = describe_node(cls)
        except Exception as exc:  # noqa: BLE001 — UI fallback path
            self._show_error(
                f"Could not introspect <code>{html.escape(cls.__name__)}</code>: "
                f"{html.escape(str(exc))}"
            )
            return
        self._body.setHtml(render_node_html(desc))

    def show_entry(self, entry: NodeEntry) -> None:
        """Render documentation for a palette :class:`NodeEntry`."""
        try:
            module = importlib.import_module(entry.module)
            cls = getattr(module, entry.class_name)
        except Exception as exc:  # noqa: BLE001 — UI fallback path
            full = f"{entry.module}.{entry.class_name}"
            self._show_error(
                f"Could not load <code>{html.escape(full)}</code>: "
                f"{html.escape(str(exc))}"
            )
            return
        self.show_class(cls)

    def clear(self) -> None:
        """Show the empty-state hint."""
        self._body.setHtml(_PANEL_CSS + _EMPTY_STATE_HTML)

    # ── Internals ──────────────────────────────────────────────────────────────

    def _show_error(self, message_html: str) -> None:
        self._body.setHtml(
            _PANEL_CSS
            + f'<span style="color: #e8a86b;">{message_html}</span>'
        )

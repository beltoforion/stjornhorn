"""Documentation panel that mirrors the currently selected node.

A dockable widget that consumes :func:`core.node_doc.describe_node` and
renders the result in two parts: a small always-visible *summary*
(node name, section, brief description — the docstring's first
paragraph) and a collapsible *details* section that holds the rest of
the docstring plus the full input / output / parameter tables.

The split keeps the panel compact at rest — most of the time the
user just needs the name and the one-line summary — while still
making the full docs reachable in two clicks: select the node, hit
*Details*. The toggle's open/closed state survives selection
changes within a session, so a user reading docs can tab between
nodes without re-opening the disclosure each time.

The panel updates from two selection sources:

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
    QFrame,
    QLabel,
    QSizePolicy,
    QTextBrowser,
    QToolButton,
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

#: CSS shared by the summary label and the details browser. Tuned for
#: a narrow dock (≈ 220 px is the realistic minimum a user wants to
#: give it): small fonts, no fixed-width meta blocks,
#: ``word-break: break-all`` on every potentially-long ``<code>``
#: span so a dotted module path or a long file-dialog filter wraps
#: instead of forcing a horizontal scrollbar. ``<dl>`` instead of
#: bullets so the param name + body lines vertically align with no
#: list-marker gutter. Colour palette mirrors the rest of the editor
#: (panel ``#2f2f33`` / muted text ``#9a9a9f`` / accent ``#f0c83c``).
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
#:
#: All seven role names that actually appear in the codebase today
#: are handled with one pattern; new roles only need to be added if
#: they contain characters outside ``[a-z]``.
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
      2. PEP-257 cleandoc — class docstrings carry their indentation,
         which would survive in HTML as awkward leading spaces in the
         middle of paragraphs. Plain ``textwrap.dedent`` is a no-op
         here because the common prefix is empty (first line has zero
         indentation, body has class-level indent); ``cleandoc``
         understands that convention.
      3. HTML-escape so user content can't smuggle markup.
      4. Re-introduce the two pieces of light formatting that survive
         escaping: RST inline code (``` ``foo`` ```) becomes
         ``<code>foo</code>``.
    """
    text = _strip_sphinx_roles(text)
    text = inspect.cleandoc(text)
    text = html.escape(text)
    text = _RST_INLINE_CODE_RE.sub(r"<code>\1</code>", text)
    return text


def _docstring_paragraphs(docstring: str) -> list[str]:
    """Split a class docstring into paragraphs, each already prose-rendered.

    The first paragraph is the convention-defined "summary" line per
    PEP 257, so the panel uses it as the always-visible brief. The
    rest live inside the collapsible details section.
    """
    if not docstring.strip():
        return []
    return [
        _render_prose(p).strip()
        for p in docstring.split("\n\n")
        if p.strip()
    ]


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
    centred-dot-separated line. Returns ``""`` when nothing useful is
    present so the caller can drop the line entirely."""
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


def render_node_summary(desc: dict) -> str:
    """HTML for the *always-visible* portion of the panel.

    Carries the node name, section, the docstring's first
    paragraph (PEP 257 summary line), and the *Inputs* and
    *Outputs* tables — the structural information a user needs to
    decide how to wire the node, which would be unhelpful behind
    a disclosure. Parameters and the rest of the docstring move
    into the collapsible :func:`render_node_details` body.

    Pure function — no Qt — so it's testable without a
    ``QApplication``.
    """
    parts: list[str] = [_PANEL_CSS]

    # H1 carries an HTML ``title`` attribute with the dotted module
    # path so a curious user can hover to see where the class lives,
    # without that long string forcing the dock open. Most QTextBrowser
    # builds honour ``title`` as a tooltip; on those that don't the
    # information is still accessible from the source.
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

    if inputs := desc.get("inputs", []):
        parts.append("<h2>Inputs</h2><dl>")
        parts.extend(_render_input(p) for p in inputs)
        parts.append("</dl>")

    if outputs := desc.get("outputs", []):
        parts.append("<h2>Outputs</h2><dl>")
        parts.extend(_render_output(p) for p in outputs)
        parts.append("</dl>")

    return "".join(parts)


def render_node_details(desc: dict) -> str:
    """HTML for the *collapsible* portion of the panel.

    Contains the rest of the docstring (paragraphs after the PEP 257
    summary line) followed by the Parameters table. Inputs and
    Outputs live in the always-visible :func:`render_node_summary`
    head — they describe how to wire the node, which is needed
    upfront. Empty sections are *omitted* entirely (a node with no
    params simply doesn't show a Parameters heading) so the body
    stays compact when the user opens the disclosure.
    """
    parts: list[str] = [_PANEL_CSS]

    # Skip the summary line; everything else from the docstring goes
    # into the details body. The summary already lives in the
    # always-visible head, so duplicating it here would just push
    # the useful content further down.
    paragraphs = _docstring_paragraphs(desc.get("docstring", ""))
    for p in paragraphs[1:]:
        parts.append(f'<p class="doc">{p}</p>')

    if params := desc.get("params", []):
        parts.append("<h2>Parameters</h2><dl>")
        parts.extend(_render_param(p) for p in params)
        parts.append("</dl>")

    return "".join(parts)


def has_details(desc: dict) -> bool:
    """``True`` when ``render_node_details`` would produce content
    beyond just the stylesheet — i.e. there *is* something for the
    user to expand. Lets the widget hide the *Details* toggle on
    nodes that have nothing more to show, instead of dangling an
    empty disclosure.

    Inputs and Outputs are *not* counted: they live in the
    always-visible summary head and are never behind the
    disclosure, so their presence shouldn't make the toggle
    appear when there's nothing else to expand into.
    """
    if any(p.strip() for p in _docstring_paragraphs(desc.get("docstring", ""))[1:]):
        return True
    if desc.get("params"):
        return True
    return False


class NodeDocPanel(QWidget):
    """Dockable panel that renders the docs of the currently selected node.

    Layout (top to bottom):
      1. Always-visible summary (``QLabel`` with rich text) —
         display name, section, brief description.
      2. Toggle button (``QToolButton``) — disclosure triangle that
         collapses / expands the details body.
      3. Collapsible details body (``QTextBrowser``) — the rest of
         the docstring plus Inputs / Outputs / Parameters.

    The toggle's expanded state is preserved across selection
    changes within the session, so a user reading docs can switch
    between nodes without re-clicking the disclosure each time.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # ``True`` while the currently-shown class has something in its
        # details body. Tracked separately from ``QWidget.isVisible``
        # because the latter depends on the parent's realised visibility
        # and gives misleading answers in unit tests where the panel is
        # never ``show()``-n.
        self._has_details: bool = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        # ── Summary head: rich-text QLabel sized to its content ───
        # Using QLabel rather than a second QTextBrowser keeps the
        # head compact (no scrollbars, no fixed default height) and
        # auto-shrinks to the prose it carries. ``setWordWrap`` is
        # essential for narrow docks; ``OpenExternalLinks`` is on
        # in case future descriptions embed an HTTP link.
        self._summary = QLabel()
        self._summary.setTextFormat(Qt.TextFormat.RichText)
        self._summary.setWordWrap(True)
        self._summary.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        self._summary.setOpenExternalLinks(True)
        self._summary.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed,
        )
        layout.addWidget(self._summary)

        # ── Toggle: flat button with disclosure arrow ────────────
        # Hidden when the current node has nothing in its details
        # body (e.g. an undocumented filter with no params); the
        # summary already says everything there is to say.
        self._toggle = QToolButton()
        self._toggle.setCheckable(True)
        self._toggle.setChecked(False)
        self._toggle.setText("Details")
        self._toggle.setArrowType(Qt.ArrowType.RightArrow)
        self._toggle.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon,
        )
        self._toggle.setAutoRaise(True)
        self._toggle.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed,
        )
        self._toggle.setStyleSheet(
            "QToolButton { color: #9a9a9f; font-size: 10px; "
            "text-transform: uppercase; letter-spacing: 0.6px; "
            "padding: 2px 0; border: none; }"
        )
        self._toggle.toggled.connect(self._on_toggle)
        layout.addWidget(self._toggle, alignment=Qt.AlignmentFlag.AlignLeft)

        # Thin separator sits between the toggle and the body so the
        # disclosure has a visible "lid" even when the body is hidden.
        # Borrowed colour from the rest of the editor's panel borders.
        self._rule = QFrame()
        self._rule.setFrameShape(QFrame.Shape.HLine)
        self._rule.setStyleSheet("color: #1a1a1d;")
        layout.addWidget(self._rule)

        # ── Details body: full-height QTextBrowser ───────────────
        self._details = QTextBrowser()
        self._details.setOpenExternalLinks(True)
        self._details.setVisible(False)
        self._details.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        layout.addWidget(self._details, 1)

        self.clear()

    # ── Public slots ───────────────────────────────────────────────────────────

    def show_class(self, cls: type[NodeBase]) -> None:
        """Render documentation for a node *class*.

        The class is instantiated via :func:`describe_node` to read
        its actual port and param shape. Failures fall back to a
        small explanatory message rather than propagating — the
        panel is supposed to be informative, not a crash surface.
        """
        try:
            desc = describe_node(cls)
        except Exception as exc:  # noqa: BLE001 — we're a UI fallback path
            self._show_error(
                f"Could not introspect <code>{html.escape(cls.__name__)}</code>: "
                f"{html.escape(str(exc))}"
            )
            return
        self._show_desc(desc)

    def show_entry(self, entry: NodeEntry) -> None:
        """Render documentation for a palette :class:`NodeEntry`.

        Imports ``entry.module`` lazily (first selection only —
        Python caches the module thereafter) and resolves the class
        via :func:`getattr`. Same fallback behaviour as
        :meth:`show_class` for failures.
        """
        try:
            module = importlib.import_module(entry.module)
            cls = getattr(module, entry.class_name)
        except Exception as exc:  # noqa: BLE001 — we're a UI fallback path
            full = f"{entry.module}.{entry.class_name}"
            self._show_error(
                f"Could not load <code>{html.escape(full)}</code>: "
                f"{html.escape(str(exc))}"
            )
            return
        self.show_class(cls)

    def clear(self) -> None:
        """Show the empty-state hint and hide the disclosure."""
        self._summary.setText(_EMPTY_STATE_HTML)
        self._details.setHtml("")
        self._has_details = False
        self._toggle.setVisible(False)
        self._rule.setVisible(False)
        self._details.setVisible(False)

    # ── Internals ──────────────────────────────────────────────────────────────

    def _show_desc(self, desc: dict) -> None:
        self._summary.setText(render_node_summary(desc))
        self._details.setHtml(render_node_details(desc))
        # Hide the disclosure entirely when there's nothing to
        # disclose, instead of dangling an empty toggle that opens
        # to a blank panel and confuses the user.
        self._has_details = has_details(desc)
        self._toggle.setVisible(self._has_details)
        self._rule.setVisible(self._has_details)
        # Body visibility follows the user's last toggle state, but
        # if there's nothing to show the body must also stay hidden.
        self._details.setVisible(self._has_details and self._toggle.isChecked())

    def _show_error(self, message_html: str) -> None:
        """Display a fallback message in the summary head and hide
        the disclosure, mirroring the empty-state shape."""
        self._summary.setText(
            f'<span style="color: #e8a86b;">{message_html}</span>'
        )
        self._details.setHtml("")
        self._has_details = False
        self._toggle.setVisible(False)
        self._rule.setVisible(False)
        self._details.setVisible(False)

    def _on_toggle(self, checked: bool) -> None:
        """React to the user toggling the disclosure: flip the arrow
        direction and show / hide the details body."""
        self._toggle.setArrowType(
            Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow,
        )
        # Only show the body when there's actually content for it.
        # ``_has_details`` mirrors ``has_details(desc)`` from the most
        # recent ``_show_desc`` call and stays meaningful regardless of
        # the panel's realised visibility (matters for headless tests).
        self._details.setVisible(checked and self._has_details)

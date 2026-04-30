"""Unit tests for the pure-function HTML renderer used by the
:class:`~ui.node_doc_panel.NodeDocPanel`.

``render_node_html`` is intentionally Qt-free so the bulk of the
documentation-display logic can be tested without a ``QApplication``;
the widget tests in ``test_node_doc_panel_widget.py`` only need to
verify that the panel actually feeds its browser through this
function.
"""
from __future__ import annotations

from ui.node_doc_panel import (
    _strip_sphinx_roles,
    render_node_html,
)


def _example_desc() -> dict:
    """A representative ``describe_node`` output covering every
    branch of the renderer in one document.

    Mirrors the shape ``core.node_doc.describe_node`` produces, with
    one of each port flavour (image-flow input, INT param port with
    bounds + unit, ENUM constant param) so every branch fires.
    """
    return {
        "class_name": "Resize",
        "display_name": "Resize",
        "section": "Transform",
        "module": "nodes.filters.resize",
        "docstring": (
            "Resize an image to an explicit (width, height) using one of "
            "three layout strategies.\n\n"
            "Output dtype and channel count match the input."
        ),
        "inputs": [
            {
                "name": "image",
                "accepted_types": ["IMAGE", "IMAGE_GREY"],
                "optional": False,
            },
            {
                "name": "width",
                "accepted_types": ["SCALAR"],
                "optional": True,
                "default": 256,
                "min": 1,
                "unit": "px",
                "description": "Target width in pixels.",
                "param_type": "INT",
            },
        ],
        "outputs": [
            {"name": "image", "emits": ["IMAGE", "IMAGE_GREY"]},
        ],
        "params": [
            {
                "name": "method",
                "default": 0,
                "description": "Layout strategy.",
                "param_type": "ENUM",
                "enum": {0: "SCALE", 1: "CROP_OR_FILL", 2: "BEST_FIT"},
            },
        ],
    }


# ── Header (name, section, module path) ───────────────────────────────────────

def test_includes_display_name_and_section() -> None:
    out = render_node_html(_example_desc())
    assert ">Resize</h1>" in out
    assert '<p class="meta">Transform</p>' in out


def test_keeps_module_path_in_h1_title_tooltip_only() -> None:
    """The dotted ``nodes.filters.resize.Resize`` is too long for
    the visible meta line in a narrow dock — it survives only as
    the H1's ``title`` tooltip."""
    out = render_node_html(_example_desc())
    assert 'title="nodes.filters.resize.Resize"' in out
    meta_inner = out.split('<p class="meta">', 1)[1].split("</p>", 1)[0]
    assert "nodes.filters.resize" not in meta_inner


# ── Docstring (brief + body paragraphs) ───────────────────────────────────────

def test_renders_brief_and_body_paragraphs() -> None:
    """The PEP 257 summary line gets ``.brief`` styling; subsequent
    paragraphs render as ``.doc`` blocks. Both appear in the same
    body — no disclosure to expand."""
    out = render_node_html(_example_desc())
    assert '<p class="brief">Resize an image to an explicit' in out
    assert '<p class="doc">Output dtype and channel count' in out


def test_renders_when_docstring_is_missing() -> None:
    desc = _example_desc()
    desc["docstring"] = ""
    out = render_node_html(desc)
    assert ">Resize</h1>" in out
    assert '<p class="brief">' not in out
    assert '<p class="doc">' not in out


# ── Inputs / Outputs / Parameters (order + presence) ──────────────────────────

def test_sections_appear_in_canonical_order() -> None:
    """Inputs, Outputs, Parameters render in that order so the user
    reads the wiring contract before the configurable knobs."""
    out = render_node_html(_example_desc())
    inputs_at = out.index("<h2>Inputs</h2>")
    outputs_at = out.index("<h2>Outputs</h2>")
    params_at = out.index("<h2>Parameters</h2>")
    assert inputs_at < outputs_at < params_at


def test_marks_required_input() -> None:
    out = render_node_html(_example_desc())
    assert "required" in out


def test_renders_param_metadata_extras() -> None:
    out = render_node_html(_example_desc())
    assert "Layout strategy." in out
    assert "default <code>0</code>" in out


def test_renders_enum_mapping() -> None:
    out = render_node_html(_example_desc())
    assert "0=SCALE" in out
    assert "1=CROP_OR_FILL" in out
    assert "2=BEST_FIT" in out


def test_omits_empty_inputs_section() -> None:
    """A source has no inputs; that absence is rendered as a missing
    section heading rather than a placeholder."""
    desc = _example_desc()
    desc["inputs"] = []
    out = render_node_html(desc)
    assert "<h2>Inputs</h2>" not in out


def test_omits_empty_parameters_section() -> None:
    desc = _example_desc()
    desc["params"] = []
    out = render_node_html(desc)
    assert "<h2>Parameters</h2>" not in out


# ── Prose cleanup (Sphinx roles, RST inline code, dedent, enum default) ───────

def test_strip_sphinx_roles_removes_role_prefix() -> None:
    """``:class:`Resize``` → ``Resize``. The role prefix is dev
    syntax leaking into user-visible text; this strips it without
    losing the back-ticked target."""
    assert _strip_sphinx_roles(":class:`Resize`") == "Resize"
    assert _strip_sphinx_roles(":func:`cv2.GaussianBlur`") == "cv2.GaussianBlur"
    assert _strip_sphinx_roles(":data:`INPUT_DIR`") == "INPUT_DIR"
    assert _strip_sphinx_roles(":attr:`Port.metadata`") == "Port.metadata"
    assert _strip_sphinx_roles(":meth:`x.do`") == "x.do"
    assert _strip_sphinx_roles(":mod:`core.foo`") == "core.foo"


def test_strip_sphinx_roles_shortens_tilde_prefix() -> None:
    """``:class:`~ui.flow_scene.FlowScene``` is Sphinx shorthand for
    "show only the last component" — the renderer mirrors that."""
    assert (
        _strip_sphinx_roles(":class:`~ui.flow_scene.FlowScene`")
        == "FlowScene"
    )


def test_strips_sphinx_roles_from_docstring() -> None:
    desc = _example_desc()
    desc["docstring"] = (
        "Wraps :func:`cv2.GaussianBlur` from the OpenCV API."
    )
    out = render_node_html(desc)
    assert ":func:" not in out
    assert "cv2.GaussianBlur" in out


def test_strips_sphinx_roles_from_param_descriptions() -> None:
    desc = _example_desc()
    desc["params"][0]["description"] = (
        "See :class:`ResizeMethod` for the choices."
    )
    out = render_node_html(desc)
    assert ":class:" not in out
    assert "ResizeMethod" in out


def test_converts_rst_inline_code_to_code_tags() -> None:
    desc = _example_desc()
    desc["docstring"] = "Wraps ``cv2.GaussianBlur`` from the OpenCV API."
    out = render_node_html(desc)
    assert "``" not in out
    assert "<code>cv2.GaussianBlur</code>" in out


def test_dedents_class_docstring() -> None:
    """Class docstrings whose first line is at column zero but body
    is indented to match the class definition come out dedented;
    otherwise leading whitespace would survive into HTML."""
    desc = _example_desc()
    desc["docstring"] = (
        "First line at column zero.\n\n"
        "    Second paragraph indented by four spaces in source."
    )
    out = render_node_html(desc)
    assert "    Second paragraph" not in out
    assert "Second paragraph indented" in out


def test_normalises_enum_default_to_member_name() -> None:
    """Python ``Enum`` members repr as ``<MyEnum.NAME: 0>`` — that
    raw form must not leak into the panel via the default-extras
    line."""
    import enum as enum_mod

    class _Method(enum_mod.IntEnum):
        SCALE = 0
        CROP = 1

    desc = _example_desc()
    desc["params"][0]["default"] = _Method.SCALE
    out = render_node_html(desc)
    assert "&lt;_Method.SCALE" not in out
    assert "default <code>SCALE</code>" in out


# ── Real-node round trip ──────────────────────────────────────────────────────

def test_real_node_round_trips_through_describe_node() -> None:
    """End-to-end: a real node class flows through ``describe_node``
    and the resulting body covers its essentials with no Sphinx
    role leakage."""
    from core.node_doc import describe_node
    from nodes.filters.gaussian_blur import GaussianBlur

    desc = describe_node(GaussianBlur)
    out = render_node_html(desc)

    assert ">Gaussian Blur</h1>" in out
    assert "<h2>Inputs</h2>" in out
    assert "<h2>Outputs</h2>" in out
    assert "ksize" in out
    assert "sigma" in out
    assert ":class:" not in out
    assert ":func:" not in out

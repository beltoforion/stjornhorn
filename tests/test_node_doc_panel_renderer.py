"""Unit tests for the pure-function HTML renderers used by the
:class:`~ui.node_doc_panel.NodeDocPanel`.

The renderers (``render_node_summary`` and ``render_node_details``)
are intentionally Qt-free so the bulk of the documentation-display
logic can be tested without a ``QApplication``; the widget tests in
``test_node_doc_panel_widget.py`` only need to verify that the
widget actually feeds its label / browser through these functions
and toggles them in the right way.
"""
from __future__ import annotations

from ui.node_doc_panel import (
    _strip_sphinx_roles,
    has_details,
    render_node_details,
    render_node_summary,
)


def _example_desc() -> dict:
    """A representative ``describe_node`` output covering every
    branch of the renderers in one document.

    Mirrors the shape ``core.node_doc.describe_node`` produces, with
    one of each port flavour (image-flow input, INT param port with
    bounds + unit, ENUM constant param) so the renderers' branches
    all exercise."""
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


# ── render_node_summary ────────────────────────────────────────────────────────

def test_summary_includes_display_name_section_and_brief() -> None:
    out = render_node_summary(_example_desc())
    assert ">Resize</h1>" in out
    assert '<p class="meta">Transform</p>' in out
    # The PEP 257 summary line — first paragraph of the docstring —
    # is always visible in the summary head.
    assert "Resize an image to an explicit" in out
    assert "three layout strategies." in out


def test_summary_does_not_include_subsequent_paragraphs() -> None:
    """The second-and-later paragraphs of the docstring belong in
    the collapsible details section so the summary stays compact."""
    out = render_node_summary(_example_desc())
    assert "Output dtype and channel count" not in out


def test_summary_keeps_module_path_in_h1_title_tooltip_only() -> None:
    """The dotted ``nodes.filters.resize.Resize`` is too long for
    the visible meta line in a narrow dock — it survives only as
    the H1's ``title`` tooltip."""
    out = render_node_summary(_example_desc())
    assert 'title="nodes.filters.resize.Resize"' in out
    # …and is NOT in the visible meta line.
    meta_inner = out.split('<p class="meta">', 1)[1].split("</p>", 1)[0]
    assert "nodes.filters.resize" not in meta_inner


def test_summary_renders_when_docstring_is_missing() -> None:
    desc = _example_desc()
    desc["docstring"] = ""
    out = render_node_summary(desc)
    assert ">Resize</h1>" in out
    assert '<p class="brief">' not in out


# ── render_node_details ────────────────────────────────────────────────────────

def test_details_omits_summary_paragraph() -> None:
    """The first paragraph already lives in the summary head; the
    details body picks up from paragraph two onwards so the user
    isn't reading the same sentence twice."""
    out = render_node_details(_example_desc())
    assert "Resize an image to an explicit" not in out
    assert "Output dtype and channel count" in out


def test_details_renders_inputs_outputs_parameters() -> None:
    out = render_node_details(_example_desc())
    assert "<h2>Inputs</h2>" in out
    assert "<h2>Outputs</h2>" in out
    assert "<h2>Parameters</h2>" in out


def test_details_marks_required_input() -> None:
    out = render_node_details(_example_desc())
    assert "required" in out


def test_details_renders_param_metadata_extras() -> None:
    out = render_node_details(_example_desc())
    assert "Target width in pixels." in out
    assert "default <code>256</code>" in out
    assert "min <code>1</code>" in out
    assert "unit <code>px</code>" in out


def test_details_renders_enum_mapping() -> None:
    out = render_node_details(_example_desc())
    assert "0=SCALE" in out
    assert "1=CROP_OR_FILL" in out
    assert "2=BEST_FIT" in out


def test_details_omits_empty_sections() -> None:
    desc = _example_desc()
    desc["params"] = []
    out = render_node_details(desc)
    assert "<h2>Parameters</h2>" not in out


# ── has_details ────────────────────────────────────────────────────────────────

def test_has_details_true_when_node_has_ports_or_extra_paragraphs() -> None:
    assert has_details(_example_desc())


def test_has_details_false_for_bare_node() -> None:
    """A node with no inputs, outputs, params, and only a
    one-paragraph docstring has nothing to expand into."""
    desc = {
        "class_name": "NoOp",
        "display_name": "No-Op",
        "section": "",
        "module": "",
        "docstring": "Does nothing.",
        "inputs": [],
        "outputs": [],
        "params": [],
    }
    assert not has_details(desc)


def test_has_details_true_for_only_extra_paragraphs() -> None:
    """Even with no ports, a multi-paragraph docstring still has
    meaningful content for the details section."""
    desc = {
        "class_name": "Doc",
        "display_name": "Doc",
        "section": "",
        "module": "",
        "docstring": "Short summary.\n\nLong elaboration here.",
        "inputs": [],
        "outputs": [],
        "params": [],
    }
    assert has_details(desc)


# ── prose cleanup (shared by both renderers) ───────────────────────────────────

def test_strip_sphinx_roles_removes_role_prefix() -> None:
    """``:class:`Resize``` → ``Resize``. The role prefix is dev
    syntax leaking into user-visible text, this strips it without
    losing the back-ticked target."""
    assert _strip_sphinx_roles(":class:`Resize`") == "Resize"
    assert _strip_sphinx_roles(":func:`cv2.GaussianBlur`") == "cv2.GaussianBlur"
    assert _strip_sphinx_roles(":data:`INPUT_DIR`") == "INPUT_DIR"
    assert _strip_sphinx_roles(":attr:`Port.metadata`") == "Port.metadata"
    assert _strip_sphinx_roles(":meth:`x.do`") == "x.do"
    assert _strip_sphinx_roles(":mod:`core.foo`") == "core.foo"


def test_strip_sphinx_roles_shortens_tilde_prefix() -> None:
    """``:class:`~ui.flow_scene.FlowScene``` is Sphinx shorthand for
    "show only the last component" — the renderers mirror that."""
    assert (
        _strip_sphinx_roles(":class:`~ui.flow_scene.FlowScene`")
        == "FlowScene"
    )


def test_summary_strips_sphinx_roles_from_brief() -> None:
    desc = _example_desc()
    desc["docstring"] = (
        "Wraps :func:`cv2.GaussianBlur` from the OpenCV API."
    )
    out = render_node_summary(desc)
    assert ":func:" not in out
    assert "cv2.GaussianBlur" in out


def test_details_strips_sphinx_roles_from_descriptions() -> None:
    desc = _example_desc()
    desc["params"][0]["description"] = (
        "See :class:`ResizeMethod` for the choices."
    )
    out = render_node_details(desc)
    assert ":class:" not in out
    assert "ResizeMethod" in out


def test_summary_converts_rst_inline_code_to_code_tags() -> None:
    desc = _example_desc()
    desc["docstring"] = "Wraps ``cv2.GaussianBlur`` from the OpenCV API."
    out = render_node_summary(desc)
    assert "``" not in out
    assert "<code>cv2.GaussianBlur</code>" in out


def test_details_dedents_class_docstring() -> None:
    """Class docstrings whose first line is at column zero but body
    is indented to match the class definition come out dedented;
    otherwise leading whitespace would survive into HTML."""
    desc = _example_desc()
    desc["docstring"] = (
        "First line at column zero.\n\n"
        "    Second paragraph indented by four spaces in source."
    )
    out = render_node_details(desc)
    assert "    Second paragraph" not in out
    assert "Second paragraph indented" in out


def test_details_normalises_enum_default_to_member_name() -> None:
    """Python ``Enum`` members repr as ``<MyEnum.NAME: 0>`` — that
    raw form must not leak into the panel via the default-extras
    line."""
    import enum as enum_mod

    class _Method(enum_mod.IntEnum):
        SCALE = 0
        CROP = 1

    desc = _example_desc()
    desc["params"][0]["default"] = _Method.SCALE
    out = render_node_details(desc)
    assert "&lt;_Method.SCALE" not in out
    assert "default <code>SCALE</code>" in out


def test_real_node_round_trips_through_describe_node() -> None:
    """End-to-end: a real node class flows through ``describe_node``
    and the resulting summary + details cover its essentials with
    no Sphinx role leakage from the docstring."""
    from core.node_doc import describe_node
    from nodes.filters.gaussian_blur import GaussianBlur

    desc = describe_node(GaussianBlur)
    summary = render_node_summary(desc)
    details = render_node_details(desc)

    assert ">Gaussian Blur</h1>" in summary
    assert ":class:" not in summary
    assert ":func:" not in summary

    assert "<h2>Inputs</h2>" in details
    assert "ksize" in details
    assert "sigma" in details
    assert ":class:" not in details
    assert ":func:" not in details

"""Unit tests for the pure-function HTML renderer used by the
:class:`~ui.node_doc_panel.NodeDocPanel`.

The renderer is intentionally Qt-free so the bulk of the
documentation-display logic can be tested without a ``QApplication``;
the widget tests in ``test_node_doc_panel_widget.py`` only need to
verify that the widget actually feeds its browser through this
function.
"""
from __future__ import annotations

from ui.node_doc_panel import _strip_sphinx_roles, render_node_doc


def _example_desc() -> dict:
    """A representative ``describe_node`` output covering every
    branch of the renderer in one document.

    Mirrors the shape ``core.node_doc.describe_node`` produces, with
    one of each port flavour (image-flow input, INT param port with
    bounds + unit, ENUM constant param) so the renderer's branches
    all exercise."""
    return {
        "class_name": "Resize",
        "display_name": "Resize",
        "section": "Transform",
        "module": "nodes.filters.resize",
        "docstring": (
            "Resize an image to an explicit (width, height) using one of "
            "three layout strategies."
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


def test_header_renders_display_name() -> None:
    out = render_node_doc(_example_desc())
    assert "<h1" in out and ">Resize</h1>" in out


def test_section_appears_in_meta_line() -> None:
    out = render_node_doc(_example_desc())
    assert '<p class="meta">Transform</p>' in out


def test_module_path_does_not_clutter_meta_line() -> None:
    """The dotted ``nodes.filters.resize.Resize`` is too long to live
    on the visible meta line in a narrow dock — it survives only as
    the H1's ``title`` tooltip so the panel stays compact."""
    out = render_node_doc(_example_desc())
    assert '<p class="meta">' in out
    # The body of the meta line is just the section, not the module.
    assert "nodes.filters.resize" not in out.split("</p>", 1)[0].split('<p class="meta">')[1]
    # …but the full path is still recoverable via the H1 tooltip.
    assert 'title="nodes.filters.resize.Resize"' in out


def test_docstring_renders_as_paragraphs_above_inputs() -> None:
    out = render_node_doc(_example_desc())
    assert "three layout strategies" in out
    assert out.index("three layout strategies") < out.index("<h2>Inputs</h2>")


def test_required_image_input_is_marked() -> None:
    out = render_node_doc(_example_desc())
    assert "image" in out
    assert "required" in out


def test_param_port_renders_type_default_min_unit() -> None:
    out = render_node_doc(_example_desc())
    assert "width" in out
    assert "INT" in out
    assert "Target width in pixels." in out
    assert "default <code>256</code>" in out
    assert "min <code>1</code>" in out
    assert "unit <code>px</code>" in out


def test_enum_param_renders_mapping() -> None:
    out = render_node_doc(_example_desc())
    assert "0=SCALE" in out
    assert "1=CROP_OR_FILL" in out
    assert "2=BEST_FIT" in out


def test_empty_sections_are_omitted_to_save_vertical_space() -> None:
    """A node with no params produces no Parameters heading at all —
    the previous ``_(none)_`` placeholder wasted vertical real estate
    in a panel that already has to compete with the Node List for
    height."""
    desc = _example_desc()
    desc["params"] = []
    out = render_node_doc(desc)
    assert "<h2>Parameters</h2>" not in out


def test_node_without_docstring_still_renders() -> None:
    desc = _example_desc()
    desc["docstring"] = ""
    out = render_node_doc(desc)
    assert ">Resize</h1>" in out
    assert "<h2>Inputs</h2>" in out


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
    "show only the last component" — the renderer mirrors that."""
    assert (
        _strip_sphinx_roles(":class:`~ui.flow_scene.FlowScene`")
        == "FlowScene"
    )


def test_renderer_strips_sphinx_roles_from_docstrings() -> None:
    """End-to-end: a docstring with Sphinx roles must not leak the
    role prefix into the rendered HTML."""
    desc = _example_desc()
    desc["docstring"] = (
        "Wraps :func:`cv2.GaussianBlur`. See :class:`Median` for the "
        "odd-kernel rule."
    )
    out = render_node_doc(desc)
    assert ":func:" not in out
    assert ":class:" not in out
    assert "cv2.GaussianBlur" in out
    assert "Median" in out


def test_renderer_strips_sphinx_roles_from_descriptions() -> None:
    """Same treatment for metadata descriptions — they also flow
    through the renderer and should not leak ``:role:`` text."""
    desc = _example_desc()
    desc["params"][0]["description"] = (
        "See :class:`ResizeMethod` for the choices."
    )
    out = render_node_doc(desc)
    assert ":class:" not in out
    assert "ResizeMethod" in out


def test_renderer_converts_rst_inline_code_to_code_tags() -> None:
    """RST inline code (``` ``foo`` ``` in source) becomes
    ``<code>foo</code>`` in the rendered HTML — otherwise users see
    the raw double-backticks as text noise."""
    desc = _example_desc()
    desc["docstring"] = "Wraps ``cv2.GaussianBlur`` from the OpenCV API."
    out = render_node_doc(desc)
    assert "``" not in out
    assert "<code>cv2.GaussianBlur</code>" in out


def test_renderer_dedents_class_docstring() -> None:
    """A class docstring whose first line has zero indentation but
    whose body is indented to match the class definition must come
    out dedented — otherwise HTML preserves the awkward leading
    spaces inside paragraphs (looks like accidental code blocks)."""
    desc = _example_desc()
    desc["docstring"] = (
        "First line at column zero.\n\n"
        "    Second paragraph indented by four spaces in source."
    )
    out = render_node_doc(desc)
    assert "First line at column zero" in out
    # Dedent removed the four-space leading indent on the second paragraph.
    assert "    Second paragraph" not in out
    assert "Second paragraph indented" in out


def test_renderer_normalises_enum_default_to_member_name() -> None:
    """Python ``Enum`` members repr as ``<MyEnum.NAME: 0>`` — that
    string would leak into the panel via the default-extras line.
    The renderer normalises it to the member name."""
    import enum as enum_mod

    class _Method(enum_mod.IntEnum):
        SCALE = 0
        CROP = 1

    desc = _example_desc()
    desc["params"][0]["default"] = _Method.SCALE
    out = render_node_doc(desc)
    assert "&lt;_Method.SCALE" not in out
    assert "default <code>SCALE</code>" in out


def test_real_node_round_trips_through_describe_node() -> None:
    """End-to-end check against the actual schema output: a real node
    class flows through ``describe_node`` and the resulting HTML
    contains its display name, a ports section, and no Sphinx role
    leakage from its docstring."""
    from core.node_doc import describe_node
    from nodes.filters.gaussian_blur import GaussianBlur

    out = render_node_doc(describe_node(GaussianBlur))
    assert ">Gaussian Blur</h1>" in out
    assert "<h2>Inputs</h2>" in out
    assert "ksize" in out
    assert "sigma" in out
    assert ":class:" not in out
    assert ":func:" not in out

"""Unit tests for the pure-function Markdown renderer used by the
:class:`~ui.node_doc_panel.NodeDocPanel`.

The renderer is intentionally Qt-free so the bulk of the
documentation-display logic can be tested without a ``QApplication``;
the widget tests in ``test_node_doc_panel_widget.py`` only need to
verify that the widget actually feeds its browser through this
function.
"""
from __future__ import annotations

from ui.node_doc_panel import render_node_doc


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


def test_header_includes_display_name_section_and_module() -> None:
    out = render_node_doc(_example_desc())
    assert "# Resize" in out
    assert "**Section:** Transform" in out
    assert "`nodes.filters.resize.Resize`" in out


def test_docstring_appears_below_header() -> None:
    out = render_node_doc(_example_desc())
    assert "three layout strategies" in out
    # Docstring sits before the Inputs section.
    assert out.index("three layout strategies") < out.index("## Inputs")


def test_required_image_input_is_marked_required() -> None:
    out = render_node_doc(_example_desc())
    assert "**image** —" in out
    assert "*(required)*" in out


def test_param_port_renders_type_default_min_unit() -> None:
    out = render_node_doc(_example_desc())
    assert "**width**" in out
    assert "*(`INT`)*" in out
    assert "Target width in pixels." in out
    assert "default `256`" in out
    assert "min `1`" in out
    assert "unit `px`" in out


def test_enum_param_renders_mapping() -> None:
    out = render_node_doc(_example_desc())
    # ENUM mapping is rendered as ``int=NAME`` pairs in numeric order.
    assert "0=SCALE" in out
    assert "1=CROP_OR_FILL" in out
    assert "2=BEST_FIT" in out


def test_node_with_no_params_renders_none_placeholder() -> None:
    """Sources have no inputs; sinks have no outputs; many filters have
    no constant params. Empty sections render as ``_(none)_`` instead
    of being omitted, so the panel layout stays predictable.
    """
    desc = _example_desc()
    desc["params"] = []
    out = render_node_doc(desc)
    assert "## Parameters" in out
    assert "_(none)_" in out


def test_node_without_docstring_still_renders() -> None:
    desc = _example_desc()
    desc["docstring"] = ""
    out = render_node_doc(desc)
    # Header and section info are still present.
    assert "# Resize" in out
    assert "## Inputs" in out


def test_real_node_round_trips_through_describe_node() -> None:
    """End-to-end check against the actual schema output: a real node
    class flows through ``describe_node`` and the resulting
    Markdown contains its display name and a ports section."""
    from core.node_doc import describe_node
    from nodes.filters.gaussian_blur import GaussianBlur

    out = render_node_doc(describe_node(GaussianBlur))
    assert "# Gaussian Blur" in out
    assert "## Inputs" in out
    assert "**ksize**" in out
    assert "**sigma**" in out

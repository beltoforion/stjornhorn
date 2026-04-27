"""Verify that ``description`` metadata on a port shows up as the
parameter widget's tooltip in the node editor.

This is the first concrete consumer of the
:mod:`core.node_doc`-aligned ``description`` metadata key. Without it
the schema-and-lint scaffolding from PR #188 would only validate
itself; this test pins down user-visible behaviour so the sweep PRs
that fill in descriptions across the node corpus have an
end-to-end target.
"""
from __future__ import annotations

import os
import sys

# Qt requires a platform plugin even for headless tests; the offscreen
# plugin avoids the libEGL / X server requirement that bare ``QApplication``
# imposes. Set before any ``PySide6`` import.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QWidget

from core.node_base import NodeParamType
from core.port import InputPort
from nodes.filters.gaussian_blur import GaussianBlur
from nodes.filters.resize import Resize
from ui.param_widgets import build_param_widget


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication(sys.argv)


def _ksize_port(node: GaussianBlur) -> InputPort:
    """Return the ``ksize`` editable input port on a GaussianBlur node."""
    for port in node.param_input_ports:
        if port.name == "ksize":
            return port
    pytest.fail("GaussianBlur lost its 'ksize' param port")


def test_widget_tooltip_carries_port_description(qapp: QApplication) -> None:
    """Building a widget for a port that declares ``description`` in
    its metadata installs that text as the widget's tooltip."""
    node = GaussianBlur()
    port = _ksize_port(node)

    widget = build_param_widget(node, port)
    assert widget is not None

    expected = port.metadata["description"]
    assert "kernel" in expected.lower(), (
        "smoke check: GaussianBlur.ksize description should mention 'kernel'"
    )
    assert widget.toolTip() == expected


def test_widget_tooltip_propagates_to_child_widgets(qapp: QApplication) -> None:
    """Qt looks tooltips up on the leaf widget under the cursor, so the
    description must be set on every QWidget descendant — otherwise
    hovering the inner :class:`QSpinBox` shows nothing."""
    node = GaussianBlur()
    port = _ksize_port(node)
    expected = port.metadata["description"]

    widget = build_param_widget(node, port)
    assert widget is not None

    children = widget.findChildren(QWidget)
    assert children, "expected the param widget to host at least one child"
    assert any(child.toolTip() == expected for child in children), (
        "the description should reach at least one hover-target child widget"
    )


def test_widget_without_description_has_empty_tooltip(qapp: QApplication) -> None:
    """A port whose metadata carries no ``description`` key must not
    fabricate a tooltip — otherwise the absence of documentation would
    be invisible during the sweep."""
    # Construct a synthetic INT port with no description; reuse the
    # GaussianBlur node as a parameter-target for the widget factory
    # since the factory only reads ``port.metadata`` and ``port.name``.
    node = GaussianBlur()
    bare_port = InputPort(
        "ksize",
        {next(iter(node.param_input_ports[0].accepted_types))},
        optional=True,
        default_value=5,
        metadata={"default": 5, "param_type": NodeParamType.INT},
    )

    widget = build_param_widget(node, bare_port)
    assert widget is not None
    assert widget.toolTip() == ""
    for child in widget.findChildren(QWidget):
        assert child.toolTip() == "", (
            f"unexpected tooltip on child {child!r}"
        )


def test_existing_child_tooltip_is_preserved(qapp: QApplication) -> None:
    """The path-style widgets ship with informative per-control
    tooltips (e.g. the eye-icon button's "Open in system image
    viewer"). The description should complement those, not overwrite
    them — otherwise the sweep would silently degrade existing UX."""
    from nodes.sources.image_source import ImageSource

    node = ImageSource()
    file_path_param = next(
        p for p in node.params if p.name == "file_path"
    )
    assert file_path_param.metadata.get("description"), (
        "ImageSource.file_path should declare a description after this PR's sweep"
    )

    widget = build_param_widget(node, file_path_param)
    assert widget is not None
    assert widget.toolTip() == file_path_param.metadata["description"]

    # The view button declares its own tooltip; we must not overwrite it.
    preserved = [
        child.toolTip() for child in widget.findChildren(QWidget)
        if child.toolTip() and child.toolTip() != file_path_param.metadata["description"]
    ]
    assert any("viewer" in t.lower() for t in preserved), (
        "FilePathParamWidget's pre-existing 'Open in system image viewer' "
        "tooltip should be preserved alongside the new description tooltip"
    )


def test_resize_method_enum_param_has_tooltip(qapp: QApplication) -> None:
    """Constant :class:`NodeParam` instances (e.g. ``Resize.method``)
    flow through the same factory as port-style params; the tooltip
    plumbing must handle both."""
    node = Resize()
    method_param = next(p for p in node.params if p.name == "method")
    expected = method_param.metadata["description"]

    widget = build_param_widget(node, method_param)
    assert widget is not None
    assert widget.toolTip() == expected

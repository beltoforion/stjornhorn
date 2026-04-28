"""Unit tests for ``FlowView.fit_to_contents``.

Locks down issue #191: Fit must resize the scene rect to the node
bounding rect plus 5% padding on each side, leave the layout centered
in that canvas, and be idempotent under repeated invocation.
"""
from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication

from core.flow import Flow
from nodes.filters.grayscale import Grayscale
from nodes.sources.image_source import ImageSource
from ui.flow_scene import FlowScene
from ui.flow_view import FlowView


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication(sys.argv)


def _populated_view() -> tuple[FlowView, FlowScene]:
    scene = FlowScene()
    scene.set_flow(Flow(name="fit_test"))
    scene.add_node(ImageSource(), QPointF(0, 0))
    scene.add_node(Grayscale(),  QPointF(400, 250))
    view = FlowView(scene)
    view.resize(800, 600)
    return view, scene


def test_fit_resizes_scene_rect_with_5pct_padding(qapp: QApplication) -> None:
    view, scene = _populated_view()
    items = scene.itemsBoundingRect()

    view.fit_to_contents()

    expected_pad_x = items.width()  * 0.05
    expected_pad_y = items.height() * 0.05
    expected = items.adjusted(-expected_pad_x, -expected_pad_y, expected_pad_x, expected_pad_y)

    actual = scene.sceneRect()
    assert actual.left()   == pytest.approx(expected.left())
    assert actual.right()  == pytest.approx(expected.right())
    assert actual.top()    == pytest.approx(expected.top())
    assert actual.bottom() == pytest.approx(expected.bottom())


def test_fit_centers_layout_in_canvas(qapp: QApplication) -> None:
    view, scene = _populated_view()
    items = scene.itemsBoundingRect()

    view.fit_to_contents()
    canvas = scene.sceneRect()

    # Equal padding on left/right and top/bottom → layout centered.
    assert (items.left() - canvas.left()) == pytest.approx(canvas.right()  - items.right())
    assert (items.top()  - canvas.top())  == pytest.approx(canvas.bottom() - items.bottom())


def test_fit_centers_viewport_on_layout(qapp: QApplication) -> None:
    """The viewport's scene-space center must match the layout center."""
    view, scene = _populated_view()
    view.show()
    qapp.processEvents()
    items = scene.itemsBoundingRect()

    view.fit_to_contents()

    viewport_center_scene = view.mapToScene(view.viewport().rect().center())
    assert viewport_center_scene.x() == pytest.approx(items.center().x(), abs=1.0)
    assert viewport_center_scene.y() == pytest.approx(items.center().y(), abs=1.0)


def test_fit_clamps_zoom_and_still_centers(qapp: QApplication) -> None:
    """Tiny layouts that would zoom past _ZOOM_MAX must still end up centered."""
    scene = FlowScene()
    scene.set_flow(Flow(name="tiny"))
    scene.add_node(ImageSource(), QPointF(0, 0))  # single small node
    view = FlowView(scene)
    view.resize(2000, 1500)  # huge viewport → fitInView would want >5× zoom
    view.show()
    qapp.processEvents()
    items = scene.itemsBoundingRect()

    view.fit_to_contents()

    assert view.transform().m11() <= view._ZOOM_MAX + 1e-9
    viewport_center_scene = view.mapToScene(view.viewport().rect().center())
    assert viewport_center_scene.x() == pytest.approx(items.center().x(), abs=1.0)
    assert viewport_center_scene.y() == pytest.approx(items.center().y(), abs=1.0)


def test_fit_is_idempotent(qapp: QApplication) -> None:
    view, scene = _populated_view()

    view.fit_to_contents()
    first = scene.sceneRect()
    view.fit_to_contents()
    second = scene.sceneRect()

    assert first.left()   == pytest.approx(second.left())
    assert first.right()  == pytest.approx(second.right())
    assert first.top()    == pytest.approx(second.top())
    assert first.bottom() == pytest.approx(second.bottom())


def test_fit_empty_scene_is_noop(qapp: QApplication) -> None:
    scene = FlowScene()
    scene.set_flow(Flow(name="empty"))
    view = FlowView(scene)
    view.resize(800, 600)
    before = scene.sceneRect()

    view.fit_to_contents()  # must not crash

    after = scene.sceneRect()
    assert before == after

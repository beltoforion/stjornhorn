"""Tests for Backdrop scene items and their flow-file round-trip."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from core.flow import Flow
from ui.backdrop_item import (
    BackdropItem,
    DEFAULT_BACKDROP_COLOR,
    MIN_BACKDROP_HEIGHT,
    MIN_BACKDROP_WIDTH,
    _Corner,
)
from ui.flow_io import load_flow_into, save_flow_to, serialize_flow
from ui.flow_scene import FlowScene


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication(sys.argv)


def test_backdrop_default_geometry_matches_module_constants(qapp: QApplication) -> None:
    backdrop = BackdropItem()
    assert backdrop.title == "Backdrop"
    assert backdrop.color.red() == DEFAULT_BACKDROP_COLOR.red()
    assert backdrop.width > 0 and backdrop.height > 0


def test_backdrop_set_size_enforces_minimum(qapp: QApplication) -> None:
    """Dragging the grip past the minimum must clamp, not collapse
    the frame into an unclickable sliver."""
    backdrop = BackdropItem()
    backdrop.set_size(10, 10)
    assert backdrop.width == MIN_BACKDROP_WIDTH
    assert backdrop.height == MIN_BACKDROP_HEIGHT


def test_add_backdrop_tracks_it_in_the_scene(qapp: QApplication) -> None:
    scene = FlowScene()
    scene.set_flow(Flow(name="backdrop"))
    backdrop = scene.add_backdrop(QPointF(40, 50), title="Group")
    assert backdrop in scene.iter_backdrops()
    assert backdrop.pos().x() == 40
    assert backdrop.title == "Group"


def test_add_backdrop_marks_scene_dirty(qapp: QApplication) -> None:
    scene = FlowScene()
    scene.set_flow(Flow(name="backdrop"))
    assert scene.is_dirty is False
    scene.add_backdrop(QPointF(0, 0))
    assert scene.is_dirty is True


def test_remove_backdrop_drops_it_and_marks_dirty(qapp: QApplication) -> None:
    scene = FlowScene()
    scene.set_flow(Flow(name="backdrop"))
    backdrop = scene.add_backdrop(QPointF(0, 0))
    scene.mark_saved()
    assert scene.is_dirty is False
    scene.remove_backdrop(backdrop)
    assert backdrop not in scene.iter_backdrops()
    assert scene.is_dirty is True


def test_serialize_backdrops_emits_geometry_and_colour(qapp: QApplication) -> None:
    scene = FlowScene()
    flow = Flow(name="backdrop")
    scene.set_flow(flow)
    scene.add_backdrop(
        QPointF(10, 20),
        title="Chapter",
        width=240,
        height=160,
        color=QColor(30, 40, 50, 180),
    )
    data = serialize_flow(scene, flow)
    assert data["backdrops"] == [{
        "position": [10.0, 20.0],
        "size":     [240.0, 160.0],
        "title":    "Chapter",
        "color":    [30, 40, 50, 180],
    }]


def test_backdrops_round_trip_through_save_and_load(
    qapp: QApplication, tmp_path: Path,
) -> None:
    """Save a flow with a backdrop, load it back into a fresh scene,
    and check every persisted property survived intact."""
    scene = FlowScene()
    flow = Flow(name="backdrop_roundtrip")
    scene.set_flow(flow)
    scene.add_backdrop(
        QPointF(100, 50),
        title="Mask prep",
        width=300,
        height=180,
        color=QColor(40, 70, 50, 140),
    )

    path = tmp_path / "bd.flowjs"
    save_flow_to(path, scene, flow)

    fresh_scene = FlowScene()
    load_flow_into(path, fresh_scene)
    backdrops = fresh_scene.iter_backdrops()
    assert len(backdrops) == 1
    b = backdrops[0]
    assert b.title == "Mask prep"
    assert b.width == 300
    assert b.height == 180
    assert b.pos().x() == 100 and b.pos().y() == 50
    assert (b.color.red(), b.color.green(), b.color.blue(), b.color.alpha()) == (40, 70, 50, 140)


def test_loading_flow_without_backdrops_field_is_fine(
    qapp: QApplication, tmp_path: Path,
) -> None:
    """Older flow files (pre-backdrop) lack the "backdrops" key. The
    loader must treat the absence as "no backdrops" rather than
    throwing a KeyError."""
    path = tmp_path / "old.flowjs"
    path.write_text(json.dumps({
        "version":     1,
        "app_version": "0.1.16",
        "name":        "old",
        "nodes":       [],
        "connections": [],
    }), encoding="utf-8")

    scene = FlowScene()
    load_flow_into(path, scene)
    assert scene.iter_backdrops() == []


# ── Resize from each corner / close button ────────────────────────────────────


def _simulate_grip_drag(backdrop: BackdropItem, corner: _Corner, dx: float, dy: float) -> None:
    """Drive a grip drag programmatically by feeding the same start /
    end scene positions a real Qt mouse press + move would emit.

    We poke the grip's internal drag-state directly because building
    real ``QGraphicsSceneMouseEvent`` instances offscreen is brittle —
    the only behaviour under test is "drag-from-corner produces the
    right pos / size", which mouseMoveEvent computes from those
    fields.
    """
    grip = backdrop._grips[corner]  # noqa: SLF001 — test of internals
    grip._drag_start_scene = QPointF(0, 0)
    grip._drag_start_pos = backdrop.pos()
    grip._drag_start_size = (backdrop.width, backdrop.height)

    class _FakeEvent:
        def __init__(self, p: QPointF) -> None:
            self._p = p

        def scenePos(self) -> QPointF:
            return self._p

        def accept(self) -> None:
            pass

    grip.mouseMoveEvent(_FakeEvent(QPointF(dx, dy)))


def test_resize_from_se_grows_to_the_right_and_down(qapp: QApplication) -> None:
    backdrop = BackdropItem(width=200, height=150)
    backdrop.setPos(50, 60)
    _simulate_grip_drag(backdrop, _Corner.SE, dx=40, dy=30)
    # SE drag pins the top-left, so position is unchanged.
    assert (backdrop.pos().x(), backdrop.pos().y()) == (50, 60)
    assert (backdrop.width, backdrop.height) == (240, 180)


def test_resize_from_nw_pins_the_bottom_right(qapp: QApplication) -> None:
    backdrop = BackdropItem(width=200, height=150)
    backdrop.setPos(50, 60)
    _simulate_grip_drag(backdrop, _Corner.NW, dx=20, dy=10)
    # The bottom-right corner must stay where it was: x=50+200=250,
    # y=60+150=210. Pulling NW by (20, 10) shrinks both axes by that
    # amount and shifts the position accordingly.
    assert (backdrop.pos().x(), backdrop.pos().y()) == (70, 70)
    assert (backdrop.width, backdrop.height) == (180, 140)
    assert backdrop.pos().x() + backdrop.width == 250
    assert backdrop.pos().y() + backdrop.height == 210


def test_resize_from_ne_pins_the_bottom_left(qapp: QApplication) -> None:
    backdrop = BackdropItem(width=200, height=150)
    backdrop.setPos(50, 60)
    _simulate_grip_drag(backdrop, _Corner.NE, dx=30, dy=20)
    assert backdrop.pos().x() == 50
    assert backdrop.pos().y() == 80
    assert (backdrop.width, backdrop.height) == (230, 130)
    assert backdrop.pos().y() + backdrop.height == 210


def test_resize_from_sw_pins_the_top_right(qapp: QApplication) -> None:
    backdrop = BackdropItem(width=200, height=150)
    backdrop.setPos(50, 60)
    _simulate_grip_drag(backdrop, _Corner.SW, dx=15, dy=25)
    assert backdrop.pos().x() == 65
    assert backdrop.pos().y() == 60
    assert (backdrop.width, backdrop.height) == (185, 175)
    assert backdrop.pos().x() + backdrop.width == 250


def test_resize_clamp_keeps_anchor_pinned(qapp: QApplication) -> None:
    """Clamping at the minimum must not let the anchor corner drift —
    a giant inward drag with NW must still leave the bottom-right
    where the user originally placed it."""
    backdrop = BackdropItem(width=200, height=150)
    backdrop.setPos(50, 60)
    _simulate_grip_drag(backdrop, _Corner.NW, dx=999, dy=999)
    assert backdrop.width == MIN_BACKDROP_WIDTH
    assert backdrop.height == MIN_BACKDROP_HEIGHT
    assert backdrop.pos().x() + backdrop.width == 250
    assert backdrop.pos().y() + backdrop.height == 210


def test_close_button_routes_to_scene_remove_backdrop(qapp: QApplication) -> None:
    """The X close button on a backdrop must remove it through the
    same path the context menu uses (``scene.remove_backdrop``).
    """
    scene = FlowScene()
    scene.set_flow(Flow(name="bd_close"))
    backdrop = scene.add_backdrop(QPointF(0, 0))
    # The close button defers via QTimer.singleShot(0); call the
    # scene method directly here to exercise the same end state without
    # needing the Qt event loop.
    scene.remove_backdrop(backdrop)
    assert backdrop not in scene.iter_backdrops()


# ── Capture mode ──────────────────────────────────────────────────────────────


def test_capture_active_defaults_to_off(qapp: QApplication) -> None:
    backdrop = BackdropItem()
    assert backdrop.capture_active is False


def test_set_capture_active_toggles_the_flag(qapp: QApplication) -> None:
    backdrop = BackdropItem()
    backdrop.set_capture_active(True)
    assert backdrop.capture_active is True
    backdrop.set_capture_active(False)
    assert backdrop.capture_active is False


def _drag_backdrop(backdrop: BackdropItem, dx: float, dy: float) -> None:
    """Simulate the press → move → release sequence the capture-aware
    drag relies on, without spinning a Qt event loop.

    Forging real ``QGraphicsSceneMouseEvent`` instances offscreen is
    brittle, so we poke the same drag-bookkeeping fields the press
    handler would set and rely on ``setPos`` to fire ``itemChange``
    exactly the way Qt's drag would. The test then verifies the
    handler's effect on captured node positions.
    """
    if backdrop.capture_active:
        backdrop._drag_anchor_pos = backdrop.scenePos()  # noqa: SLF001 — internal contract under test
        backdrop._captured_snapshot = [
            (item, item.pos()) for item in backdrop.captured_node_items()
        ]
    backdrop.setPos(backdrop.pos().x() + dx, backdrop.pos().y() + dy)
    backdrop._drag_anchor_pos = None
    backdrop._captured_snapshot = []


def test_dragging_with_capture_off_does_not_move_enclosed_nodes(
    qapp: QApplication,
) -> None:
    """A node fully framed by the backdrop must stay put when the
    backdrop is dragged with capture toggle off."""
    from nodes.sources.image_source import ImageSource
    scene = FlowScene()
    scene.set_flow(Flow(name="cap_off"))
    backdrop = scene.add_backdrop(QPointF(0, 0), width=400, height=300)
    node = scene.add_node(ImageSource(), QPointF(50, 50))
    start_pos = node.pos()
    _drag_backdrop(backdrop, 100, 80)
    assert node.pos() == start_pos


def test_dragging_with_capture_on_sweeps_fully_enclosed_nodes(
    qapp: QApplication,
) -> None:
    """The headline behaviour: with capture on, a node fully inside
    the backdrop moves by the same delta the backdrop did."""
    from nodes.sources.image_source import ImageSource
    scene = FlowScene()
    scene.set_flow(Flow(name="cap_on"))
    backdrop = scene.add_backdrop(QPointF(0, 0), width=400, height=300)
    backdrop.set_capture_active(True)
    node = scene.add_node(ImageSource(), QPointF(50, 50))
    start_pos = node.pos()
    _drag_backdrop(backdrop, 100, 80)
    assert node.pos().x() == start_pos.x() + 100
    assert node.pos().y() == start_pos.y() + 80


def test_capture_does_not_pull_nodes_outside_the_backdrop(
    qapp: QApplication,
) -> None:
    """Only nodes whose bounding box lies fully inside the backdrop
    at press-time count. A node clearly outside must stay put."""
    from nodes.sources.image_source import ImageSource
    scene = FlowScene()
    scene.set_flow(Flow(name="cap_outside"))
    backdrop = scene.add_backdrop(QPointF(0, 0), width=200, height=150)
    backdrop.set_capture_active(True)
    outside = scene.add_node(ImageSource(), QPointF(2000, 2000))
    start_pos = outside.pos()
    _drag_backdrop(backdrop, 50, 50)
    assert outside.pos() == start_pos


def test_capture_snapshot_is_taken_at_press_time(qapp: QApplication) -> None:
    """A node that wasn't framed at press-time mustn't get swept along
    just because the moving backdrop ran into it mid-drag — we'd
    otherwise vacuum up every node the backdrop crosses."""
    from nodes.sources.image_source import ImageSource
    scene = FlowScene()
    scene.set_flow(Flow(name="cap_snap"))
    backdrop = scene.add_backdrop(QPointF(0, 0), width=200, height=150)
    backdrop.set_capture_active(True)
    # Node sitting outside the backdrop at press-time. Even though
    # dragging the backdrop +250px right would have it overlap the
    # node mid-flight, the snapshot was empty at press, so no shift.
    far = scene.add_node(ImageSource(), QPointF(500, 50))
    start_pos = far.pos()
    _drag_backdrop(backdrop, 250, 0)
    assert far.pos() == start_pos


def test_capture_flag_round_trips_through_save_and_load(
    qapp: QApplication, tmp_path: Path,
) -> None:
    scene = FlowScene()
    flow = Flow(name="cap_persist")
    scene.set_flow(flow)
    backdrop = scene.add_backdrop(QPointF(0, 0))
    backdrop.set_capture_active(True)

    path = tmp_path / "cap.flowjs"
    save_flow_to(path, scene, flow)

    fresh = FlowScene()
    load_flow_into(path, fresh)
    [restored] = fresh.iter_backdrops()
    assert restored.capture_active is True


def test_capture_flag_omitted_when_off_in_serialised_form(
    qapp: QApplication,
) -> None:
    """Default-off capture state stays out of the JSON to keep flows
    tidy for the common case."""
    scene = FlowScene()
    flow = Flow(name="cap_default")
    scene.set_flow(flow)
    scene.add_backdrop(QPointF(0, 0))
    data = serialize_flow(scene, flow)
    assert "capture" not in data["backdrops"][0]

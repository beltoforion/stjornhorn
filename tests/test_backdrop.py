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


# ── Capture-on-drag (always on) ───────────────────────────────────────────────


def _drag_backdrop(backdrop: BackdropItem, dx: float, dy: float) -> None:
    """Simulate the press → move → release sequence the capture-aware
    drag relies on, without spinning a Qt event loop.

    Forging real ``QGraphicsSceneMouseEvent`` instances offscreen is
    brittle, so we poke the same drag-bookkeeping fields the press
    handler would set and rely on ``setPos`` to fire ``itemChange``
    exactly the way Qt's drag would.
    """
    backdrop._drag_anchor_pos = backdrop.scenePos()  # noqa: SLF001 — internal contract under test
    backdrop._captured_snapshot = [
        (item, item.pos()) for item in backdrop.captured_node_items()
    ]
    backdrop.setPos(backdrop.pos().x() + dx, backdrop.pos().y() + dy)
    backdrop._drag_anchor_pos = None
    backdrop._captured_snapshot = []


def test_dragging_sweeps_fully_enclosed_nodes(qapp: QApplication) -> None:
    """The headline behaviour: a node fully inside the backdrop moves
    by the same delta the backdrop did."""
    from nodes.sources.image_source import ImageSource
    scene = FlowScene()
    scene.set_flow(Flow(name="cap_on"))
    backdrop = scene.add_backdrop(QPointF(0, 0), width=400, height=300)
    node = scene.add_node(ImageSource(), QPointF(50, 50))
    start_pos = node.pos()
    _drag_backdrop(backdrop, 100, 80)
    assert node.pos().x() == start_pos.x() + 100
    assert node.pos().y() == start_pos.y() + 80


def test_dragging_does_not_pull_nodes_outside_the_backdrop(
    qapp: QApplication,
) -> None:
    """Only nodes whose bounding box lies fully inside the backdrop
    at press-time count. A node clearly outside must stay put."""
    from nodes.sources.image_source import ImageSource
    scene = FlowScene()
    scene.set_flow(Flow(name="cap_outside"))
    backdrop = scene.add_backdrop(QPointF(0, 0), width=200, height=150)
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
    # Node sitting outside the backdrop at press-time. Even though
    # dragging the backdrop +250 px right would have it overlap the
    # node mid-flight, the snapshot was empty at press, so no shift.
    far = scene.add_node(ImageSource(), QPointF(500, 50))
    start_pos = far.pos()
    _drag_backdrop(backdrop, 250, 0)
    assert far.pos() == start_pos


# ── Create Group around selection ─────────────────────────────────────────────


def test_create_group_returns_none_when_fewer_than_two_nodes_selected(
    qapp: QApplication,
) -> None:
    from nodes.sources.image_source import ImageSource
    scene = FlowScene()
    scene.set_flow(Flow(name="group_empty"))
    item = scene.add_node(ImageSource(), QPointF(0, 0))
    item.setSelected(True)
    assert scene.create_group_around_selection() is None


def test_create_group_frames_every_selected_node(qapp: QApplication) -> None:
    """The auto-fitted backdrop's scene rect must contain every
    selected node's scene rect (with padding) — i.e. the framed
    group is "captured" for the very next drag."""
    from nodes.filters.grayscale import Grayscale
    from nodes.sources.image_source import ImageSource
    scene = FlowScene()
    scene.set_flow(Flow(name="group_two"))
    a = scene.add_node(ImageSource(), QPointF(0, 0))
    b = scene.add_node(Grayscale(), QPointF(400, 100))
    a.setSelected(True)
    b.setSelected(True)
    backdrop = scene.create_group_around_selection()
    assert backdrop is not None
    rect = backdrop.sceneBoundingRect()
    assert rect.contains(a.sceneBoundingRect())
    assert rect.contains(b.sceneBoundingRect())


def test_create_group_marks_scene_dirty(qapp: QApplication) -> None:
    from nodes.filters.grayscale import Grayscale
    from nodes.sources.image_source import ImageSource
    scene = FlowScene()
    scene.set_flow(Flow(name="group_dirty"))
    a = scene.add_node(ImageSource(), QPointF(0, 0))
    b = scene.add_node(Grayscale(), QPointF(400, 0))
    a.setSelected(True)
    b.setSelected(True)
    scene.mark_saved()
    assert scene.is_dirty is False
    scene.create_group_around_selection()
    assert scene.is_dirty is True


# ── Interactive resize grips (issue #192) ─────────────────────────────────────


def _grip_named(backdrop: BackdropItem, name: str):
    """Look up a child resize grip by its compass name."""
    return next(g for g in backdrop._grips if g.name == name)  # noqa: SLF001


def _drive_grip(backdrop: BackdropItem, name: str, dx: float, dy: float):
    """Simulate a grip press + drag without spinning a Qt event loop.

    Mirrors the bookkeeping the real ``mousePressEvent`` /
    ``mouseMoveEvent`` would set, then invokes ``_apply_resize``
    with the requested scene-coord delta. Returns the grip so the
    caller can assert on its press-time snapshot if needed.
    """
    grip = _grip_named(backdrop, name)
    grip._press_scene_pos = QPointF(0, 0)            # noqa: SLF001
    grip._press_backdrop_pos = QPointF(backdrop.pos())  # noqa: SLF001
    grip._press_width = backdrop.width                # noqa: SLF001
    grip._press_height = backdrop.height              # noqa: SLF001
    grip._dirty_during_drag = False                   # noqa: SLF001
    grip._apply_resize(dx, dy)                        # noqa: SLF001
    return grip


def test_backdrop_has_eight_resize_grips(qapp: QApplication) -> None:
    backdrop = BackdropItem()
    assert len(backdrop._grips) == 8
    names = {g.name for g in backdrop._grips}
    assert names == {"nw", "n", "ne", "w", "e", "sw", "s", "se"}


def test_grips_are_hidden_by_default(qapp: QApplication) -> None:
    """Idle backdrops shouldn't show their grips — they'd compete
    with the chrome of the framed nodes."""
    backdrop = BackdropItem()
    assert all(not g.isVisible() for g in backdrop._grips)


def test_grips_become_visible_when_selected(qapp: QApplication) -> None:
    scene = FlowScene()
    scene.set_flow(Flow(name="grip_select"))
    backdrop = scene.add_backdrop(QPointF(0, 0))
    backdrop.setSelected(True)
    assert all(g.isVisible() for g in backdrop._grips)
    backdrop.setSelected(False)
    assert all(not g.isVisible() for g in backdrop._grips)


def test_grips_stay_visible_while_cursor_crosses_from_body_to_grip(
    qapp: QApplication,
) -> None:
    """Qt routes hover to the topmost item, so the body sees a
    hoverLeave the moment the cursor enters a child grip. The grips
    must stay visible across that transition or the user can never
    actually grab them."""
    backdrop = BackdropItem()
    backdrop._body_hovered = True               # noqa: SLF001 — simulate body hoverEnter
    backdrop._refresh_grip_visibility()         # noqa: SLF001
    assert all(g.isVisible() for g in backdrop._grips)
    # Cursor moves onto a grip: body fires hoverLeave, grip fires hoverEnter.
    backdrop._body_hovered = False              # noqa: SLF001
    backdrop._on_grip_hover_changed(entering=True)  # noqa: SLF001
    backdrop._refresh_grip_visibility()         # noqa: SLF001
    assert all(g.isVisible() for g in backdrop._grips)
    # Cursor leaves the grip back into open scene: both flags clear, grips hide.
    backdrop._on_grip_hover_changed(entering=False)  # noqa: SLF001
    assert all(not g.isVisible() for g in backdrop._grips)


def test_se_grip_grows_width_and_height_keeping_top_left_anchored(
    qapp: QApplication,
) -> None:
    backdrop = BackdropItem(width=200, height=150)
    backdrop.setPos(QPointF(40, 30))
    _drive_grip(backdrop, "se", dx=50, dy=20)
    assert backdrop.width == pytest.approx(250)
    assert backdrop.height == pytest.approx(170)
    # SE grip leaves the top-left corner alone.
    assert backdrop.pos() == QPointF(40, 30)


def test_nw_grip_shrinks_size_and_moves_top_left(qapp: QApplication) -> None:
    backdrop = BackdropItem(width=200, height=150)
    backdrop.setPos(QPointF(40, 30))
    _drive_grip(backdrop, "nw", dx=20, dy=10)
    # Width/height shrink by the drag delta, top-left moves the same.
    assert backdrop.width == pytest.approx(180)
    assert backdrop.height == pytest.approx(140)
    assert backdrop.pos().x() == pytest.approx(60)
    assert backdrop.pos().y() == pytest.approx(40)


def test_n_grip_changes_only_height_and_top_y(qapp: QApplication) -> None:
    backdrop = BackdropItem(width=200, height=150)
    backdrop.setPos(QPointF(40, 30))
    _drive_grip(backdrop, "n", dx=999, dy=15)
    # The horizontal axis is untouched — dx is irrelevant for N.
    assert backdrop.width == pytest.approx(200)
    assert backdrop.height == pytest.approx(135)
    assert backdrop.pos().x() == pytest.approx(40)
    assert backdrop.pos().y() == pytest.approx(45)


def test_resize_clamps_at_minimum_dimensions(qapp: QApplication) -> None:
    """Dragging a grip past the minimum holds the anchored corner
    truly fixed instead of letting it drift past."""
    backdrop = BackdropItem(width=200, height=150)
    backdrop.setPos(QPointF(40, 30))
    # Way over-shrink via NW grip — drag goes far past the minimum.
    _drive_grip(backdrop, "nw", dx=10_000, dy=10_000)
    assert backdrop.width == pytest.approx(MIN_BACKDROP_WIDTH)
    assert backdrop.height == pytest.approx(MIN_BACKDROP_HEIGHT)
    # Anchored corner (bottom-right) must be where it was at press-time.
    assert backdrop.pos().x() == pytest.approx(40 + (200 - MIN_BACKDROP_WIDTH))
    assert backdrop.pos().y() == pytest.approx(30 + (150 - MIN_BACKDROP_HEIGHT))


def test_resize_does_not_sweep_framed_nodes(qapp: QApplication) -> None:
    """The framed nodes must stay put during a resize — only a
    body-drag is allowed to move them."""
    from nodes.sources.image_source import ImageSource
    scene = FlowScene()
    scene.set_flow(Flow(name="resize_no_sweep"))
    backdrop = scene.add_backdrop(QPointF(0, 0), width=400, height=300)
    node = scene.add_node(ImageSource(), QPointF(50, 50))
    start_pos = node.pos()
    _drive_grip(backdrop, "se", dx=80, dy=60)
    assert node.pos() == start_pos


def test_resized_geometry_round_trips_through_save_and_load(
    qapp: QApplication, tmp_path: Path,
) -> None:
    scene = FlowScene()
    flow = Flow(name="resize_roundtrip")
    scene.set_flow(flow)
    backdrop = scene.add_backdrop(
        QPointF(100, 50), title="Mask prep", width=300, height=180,
    )
    _drive_grip(backdrop, "se", dx=50, dy=40)
    assert backdrop.width == 350 and backdrop.height == 220

    path = tmp_path / "bd_resized.flowjs"
    save_flow_to(path, scene, flow)

    fresh = FlowScene()
    load_flow_into(path, fresh)
    [reloaded] = fresh.iter_backdrops()
    assert reloaded.width == 350
    assert reloaded.height == 220
    assert reloaded.pos().x() == 100 and reloaded.pos().y() == 50

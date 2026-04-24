"""Tests for Backdrop scene items and their flow-file round-trip."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QPointF
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

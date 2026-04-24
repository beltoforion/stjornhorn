"""Unit tests for FlowScene's dirty-tracking state.

The editor's "● Unsaved changes" affordance is driven by
:attr:`FlowScene.is_dirty` + :attr:`FlowScene.dirty_changed`. These
tests lock down the transitions: a fresh scene is clean, every
structural or parameter edit flips it to dirty, and only
:meth:`mark_saved` / :meth:`set_flow` clear it.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Headless Qt: must be set before PySide6 is imported anywhere.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication

from core.flow import Flow
from nodes.filters.grayscale import Grayscale
from nodes.sources.image_source import ImageSource
from ui.flow_scene import FlowScene


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication(sys.argv)


def _fresh_scene() -> FlowScene:
    scene = FlowScene()
    scene.set_flow(Flow(name="dirty_test"))
    return scene


def test_fresh_scene_is_clean(qapp: QApplication) -> None:
    scene = _fresh_scene()
    assert scene.is_dirty is False


def test_add_node_marks_dirty(qapp: QApplication) -> None:
    scene = _fresh_scene()
    scene.add_node(ImageSource(), QPointF(0, 0))
    assert scene.is_dirty is True


def test_remove_node_marks_dirty(qapp: QApplication) -> None:
    scene = _fresh_scene()
    item = scene.add_node(ImageSource(), QPointF(0, 0))
    scene.mark_saved()
    assert scene.is_dirty is False
    scene.remove_node_item(item)
    assert scene.is_dirty is True


def test_connect_ports_marks_dirty(qapp: QApplication) -> None:
    scene = _fresh_scene()
    src_item = scene.add_node(ImageSource(), QPointF(0, 0))
    dst_item = scene.add_node(Grayscale(), QPointF(200, 0))
    scene.mark_saved()
    assert scene.is_dirty is False
    scene.connect_ports(src_item.output_ports[0], dst_item.input_ports[0])
    assert scene.is_dirty is True


def test_disconnect_link_marks_dirty(qapp: QApplication) -> None:
    scene = _fresh_scene()
    src_item = scene.add_node(ImageSource(), QPointF(0, 0))
    dst_item = scene.add_node(Grayscale(), QPointF(200, 0))
    link = scene.connect_ports(
        src_item.output_ports[0], dst_item.input_ports[0]
    )
    assert link is not None
    scene.mark_saved()
    assert scene.is_dirty is False
    scene._delete_link_item(link)
    assert scene.is_dirty is True


def test_param_changed_marks_dirty(qapp: QApplication) -> None:
    """A param-widget edit anywhere in the scene flips dirty on."""
    scene = _fresh_scene()
    scene.add_node(ImageSource(), QPointF(0, 0))
    scene.mark_saved()
    assert scene.is_dirty is False
    scene.param_changed.emit()
    assert scene.is_dirty is True


def test_set_flow_clears_dirty(qapp: QApplication) -> None:
    """Loading / creating a new flow starts a fresh clean slate."""
    scene = _fresh_scene()
    scene.add_node(ImageSource(), QPointF(0, 0))
    assert scene.is_dirty is True
    scene.set_flow(Flow(name="another"))
    assert scene.is_dirty is False


def test_dirty_changed_emits_only_on_transitions(qapp: QApplication) -> None:
    """Back-to-back edits must not spam dirty_changed with True."""
    scene = _fresh_scene()
    events: list[bool] = []
    scene.dirty_changed.connect(events.append)

    # Two structural edits in a row: only the first should emit.
    scene.add_node(ImageSource(), QPointF(0, 0))
    scene.add_node(Grayscale(), QPointF(200, 0))
    assert events == [True]

    scene.mark_saved()
    assert events == [True, False]

    # Saving a clean scene is a no-op on the signal.
    scene.mark_saved()
    assert events == [True, False]

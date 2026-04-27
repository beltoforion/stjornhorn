"""Round-trip tests for the dock-layout persistence helper.

Issue: #183
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

# Headless Qt: must be set before PySide6 is imported anywhere.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDockWidget, QMainWindow, QWidget

from ui.dock_layout import restore_dock_layout, save_dock_layout


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication(sys.argv)


def _make_window() -> QMainWindow:
    """Build a QMainWindow with two named docks for round-trip testing."""
    win = QMainWindow()
    win.resize(800, 600)
    left_dock = QDockWidget("Left", win)
    left_dock.setObjectName("LeftDock")
    left_dock.setWidget(QWidget())
    right_dock = QDockWidget("Right", win)
    right_dock.setObjectName("RightDock")
    right_dock.setWidget(QWidget())
    win.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, left_dock)
    win.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, right_dock)
    return win


def test_save_then_restore_round_trips_dock_areas(
    qapp: QApplication,
    tmp_path: Path,
) -> None:
    layout_file = tmp_path / "dock_layout.json"

    source = _make_window()
    # Move the right dock to the bottom area so the saved state differs
    # from the default we'll set up on the destination window.
    right_dock = source.findChild(QDockWidget, "RightDock")
    assert right_dock is not None
    source.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, right_dock)

    save_dock_layout(source, layout_file)
    assert layout_file.exists()

    target = _make_window()
    target_right = target.findChild(QDockWidget, "RightDock")
    assert target_right is not None
    assert target.dockWidgetArea(target_right) == Qt.DockWidgetArea.RightDockWidgetArea

    assert restore_dock_layout(target, layout_file) is True
    assert target.dockWidgetArea(target_right) == Qt.DockWidgetArea.BottomDockWidgetArea


def test_restore_missing_file_is_silent_noop(
    qapp: QApplication,
    tmp_path: Path,
) -> None:
    layout_file = tmp_path / "absent.json"
    win = _make_window()
    assert restore_dock_layout(win, layout_file) is False


def test_restore_corrupt_payload_falls_back_to_defaults(
    qapp: QApplication,
    tmp_path: Path,
) -> None:
    layout_file = tmp_path / "garbage.json"
    layout_file.write_text("{ this is not json", encoding="utf-8")
    win = _make_window()
    assert restore_dock_layout(win, layout_file) is False


def test_restore_wrong_version_is_ignored(
    qapp: QApplication,
    tmp_path: Path,
) -> None:
    layout_file = tmp_path / "stale.json"
    layout_file.write_text(
        json.dumps({"version": 99999, "state": "AAAA"}),
        encoding="utf-8",
    )
    win = _make_window()
    assert restore_dock_layout(win, layout_file) is False


def test_restore_invalid_base64_is_ignored(
    qapp: QApplication,
    tmp_path: Path,
) -> None:
    layout_file = tmp_path / "badb64.json"
    layout_file.write_text(
        json.dumps({"version": 1, "state": "@@@not-base64@@@"}),
        encoding="utf-8",
    )
    win = _make_window()
    assert restore_dock_layout(win, layout_file) is False

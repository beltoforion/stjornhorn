"""Unit tests for NodeEditorPage's Save As behavior.

Regression coverage for the bug where Save As serialized the *old* flow
name into the JSON file because the in-memory rename happened only after
the write.
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

from PySide6.QtWidgets import QApplication

from core.flow import Flow
from core.node_registry import NodeRegistry
from ui import node_editor_page as nep
from ui.node_editor_page import NodeEditorPage


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication(sys.argv)


def test_save_as_writes_new_name_to_json(
    qapp: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = NodeEditorPage(NodeRegistry())
    page.set_flow(Flow(name="original"))

    target = tmp_path / "renamed.flowjs"
    monkeypatch.setattr(
        nep.QFileDialog,
        "getSaveFileName",
        staticmethod(lambda *a, **kw: (str(target), "")),
    )

    page._on_save_as_clicked()

    assert target.exists(), "save-as did not write the chosen file"
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["name"] == "renamed", (
        f"saved JSON still carries old flow name: {data['name']!r}"
    )
    assert page._flow is not None
    assert page._flow.name == "renamed"


def test_save_as_restores_old_name_when_write_fails(
    qapp: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = NodeEditorPage(NodeRegistry())
    page.set_flow(Flow(name="original"))

    target = tmp_path / "renamed.flowjs"
    monkeypatch.setattr(
        nep.QFileDialog,
        "getSaveFileName",
        staticmethod(lambda *a, **kw: (str(target), "")),
    )

    def _boom(*_a, **_kw) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(nep, "save_flow_to", _boom)

    page._on_save_as_clicked()

    assert not target.exists()
    assert page._flow is not None
    assert page._flow.name == "original", (
        "flow name should revert when the save-as write fails"
    )

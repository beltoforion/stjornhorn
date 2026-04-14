from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QWidget,
)

from constants import INPUT_DIR, OUTPUT_DIR
from core.node_base import NodeBase, NodeParam, NodeParamType

logger = logging.getLogger(__name__)

_SAVE_FILTER = "Images (*.png *.jpg *.jpeg)"
_OPEN_FILTER = (
    "Images / video (*.png *.jpg *.jpeg *.mp4 *.cr2);;"
    "All files (*)"
)


def build_param_widget(node: NodeBase, param: NodeParam) -> QWidget | None:
    """Return a widget that edits ``param`` on ``node``.

    The widget hooks onto the relevant value-changed signal and writes back
    to the node via ``setattr`` (matching the declarative ``NodeParam`` →
    attribute convention used by every concrete node).

    Returns ``None`` for unsupported param types, so callers can render a
    placeholder label instead of crashing.
    """
    builder = _PARAM_BUILDERS.get(param.param_type)
    if builder is None:
        logger.warning("No Qt builder registered for param type %s", param.param_type)
        return None
    return builder(node, param)


# ── Builders ───────────────────────────────────────────────────────────────────

def _build_file_path_param(node: NodeBase, param: NodeParam) -> QWidget:
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)

    line = QLineEdit(str(param.metadata.get("default", "")))
    line.setPlaceholderText("Select a file…")
    line.setMinimumWidth(180)
    line.textChanged.connect(_make_setter(node, param.name))
    layout.addWidget(line, 1)

    browse = QPushButton("…")
    browse.setFixedWidth(28)
    browse.clicked.connect(_make_browse_handler(
        line_edit=line,
        is_save=param.metadata.get("mode") == "save",
    ))
    layout.addWidget(browse, 0)

    return container


def _build_int_param(node: NodeBase, param: NodeParam) -> QWidget:
    spin = QSpinBox()
    spin.setRange(-10_000_000, 10_000_000)
    spin.setValue(int(param.metadata.get("default", 0)))
    spin.valueChanged.connect(_make_setter(node, param.name))
    spin.setAlignment(Qt.AlignRight)
    spin.setMinimumWidth(96)
    return spin


_PARAM_BUILDERS: dict[NodeParamType, Callable[[NodeBase, NodeParam], QWidget]] = {
    NodeParamType.FILE_PATH: _build_file_path_param,
    NodeParamType.INT:       _build_int_param,
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_setter(node: NodeBase, name: str) -> Callable[[object], None]:
    """Return a slot that writes the received value into ``node.<name>``."""
    def _set(value: object) -> None:
        try:
            setattr(node, name, value)
        except Exception:
            logger.exception("Failed to set %s.%s = %r", type(node).__name__, name, value)
    return _set


def _make_browse_handler(*, line_edit: QLineEdit, is_save: bool) -> Callable[[], None]:
    """Return a slot that pops up a QFileDialog and writes the result back.

    The starting directory is the directory of the current input-text value
    when it exists; otherwise :data:`OUTPUT_DIR` for save mode and
    :data:`INPUT_DIR` for load mode.
    """
    def _browse() -> None:
        current = line_edit.text() or ""
        folder = Path(current).parent.resolve()
        fallback = OUTPUT_DIR if is_save else INPUT_DIR
        initial = str(folder) if folder.is_dir() else str(fallback)

        if is_save:
            path, _ = QFileDialog.getSaveFileName(
                line_edit, "Save File As", initial, _SAVE_FILTER,
            )
        else:
            path, _ = QFileDialog.getOpenFileName(
                line_edit, "Select File", initial, _OPEN_FILTER,
            )
        if path:
            line_edit.setText(path)

    return _browse

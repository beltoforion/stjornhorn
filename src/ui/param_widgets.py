from __future__ import annotations

import logging
from pathlib import Path

from typing_extensions import override

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
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


class ParamWidgetBase(QWidget):
    """Base class for all parameter editor widgets embedded in a NodeItem.

    Each subclass binds to a single :class:`NodeParam` on a
    :class:`NodeBase` instance and exposes a uniform
    :meth:`set_value` / :meth:`get_value` interface so callers can
    refresh or read widget state without knowing the concrete type.
    """

    #: Emitted after any user interaction that commits a new value.
    value_changed = Signal(object)

    def __init__(self, node: NodeBase, param: NodeParam) -> None:
        if type(self) is ParamWidgetBase:
            raise TypeError("ParamWidgetBase cannot be instantiated directly")
        super().__init__()
        self._node = node
        self._param = param

    def set_value(self, value: object) -> None:
        """Update the widget to display *value*."""
        raise NotImplementedError

    def get_value(self) -> object:
        """Return the widget's current value."""
        raise NotImplementedError

    # ── Helpers shared by all subclasses ───────────────────────────────────────

    def _initial_value(self, fallback: object) -> object:
        """Return the value the widget should display on first creation.

        Prefers the node's current attribute (so loaded flows show their
        saved values) and falls back to the metadata default (so
        freshly-instantiated nodes still get the right starting text even if
        the subclass forgot :meth:`NodeBase._apply_default_params`).
        """
        if hasattr(self._node, self._param.name):
            return getattr(self._node, self._param.name)
        return self._param.metadata.get("default", fallback)

    def _write_to_node(self, value: object) -> None:
        """Write *value* to the node attribute, logging any error."""
        try:
            setattr(self._node, self._param.name, value)
        except Exception:
            logger.exception(
                "Failed to set %s.%s = %r",
                type(self._node).__name__, self._param.name, value,
            )


# ── Concrete widgets ───────────────────────────────────────────────────────────

class IntParamWidget(ParamWidgetBase):
    """Spin-box editor for :attr:`NodeParamType.INT` parameters."""

    def __init__(self, node: NodeBase, param: NodeParam) -> None:
        super().__init__(node, param)
        self._spin = QSpinBox()
        self._spin.setRange(-10_000_000, 10_000_000)
        self._spin.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._spin.setMinimumWidth(96)
        self._spin.valueChanged.connect(self._on_value_changed)
        self._spin.setValue(int(self._initial_value(0)))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._spin)

    def _on_value_changed(self, value: int) -> None:
        self._write_to_node(value)
        self.value_changed.emit(value)

    @override
    def set_value(self, value: object) -> None:
        self._spin.setValue(int(value))

    @override
    def get_value(self) -> object:
        return self._spin.value()


class BoolParamWidget(ParamWidgetBase):
    """Check-box editor for :attr:`NodeParamType.BOOL` parameters."""

    def __init__(self, node: NodeBase, param: NodeParam) -> None:
        super().__init__(node, param)
        self._check = QCheckBox()
        self._check.toggled.connect(self._on_value_changed)
        self._check.setChecked(bool(self._initial_value(False)))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._check)

    def _on_value_changed(self, value: bool) -> None:
        self._write_to_node(value)
        self.value_changed.emit(value)

    @override
    def set_value(self, value: object) -> None:
        self._check.setChecked(bool(value))

    @override
    def get_value(self) -> object:
        return self._check.isChecked()


class FilePathParamWidget(ParamWidgetBase):
    """Line-edit + browse-button editor for :attr:`NodeParamType.FILE_PATH` parameters."""

    def __init__(self, node: NodeBase, param: NodeParam) -> None:
        super().__init__(node, param)
        self._is_save = param.metadata.get("mode") == "save"

        self._line = QLineEdit()
        self._line.setPlaceholderText("Select a file…")
        # Min width must leave room for the 28 px browse button + spacing
        # inside the fixed-width node body, otherwise the line edit overflows
        # and visually overlaps the button.
        self._line.setMinimumWidth(80)
        self._line.textChanged.connect(self._on_value_changed)
        self._line.setText(str(self._initial_value("")))

        browse = QPushButton("…")
        browse.setFixedWidth(28)
        browse.clicked.connect(self._browse)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self._line, 1)
        layout.addWidget(browse, 0)

    def _on_value_changed(self, value: str) -> None:
        self._write_to_node(value)
        self.value_changed.emit(value)

    @override
    def set_value(self, value: object) -> None:
        self._line.setText(str(value))

    @override
    def get_value(self) -> object:
        return self._line.text()

    def _browse(self) -> None:
        current = self._line.text() or ""
        folder = Path(current).parent.resolve()
        fallback = OUTPUT_DIR if self._is_save else INPUT_DIR
        initial = str(folder) if folder.is_dir() else str(fallback)

        if self._is_save:
            path, _ = QFileDialog.getSaveFileName(
                self._line, "Save File As", initial, _SAVE_FILTER,
            )
        else:
            path, _ = QFileDialog.getOpenFileName(
                self._line, "Select File", initial, _OPEN_FILTER,
            )
        if path:
            self._line.setText(path)


# ── Registry & factory ─────────────────────────────────────────────────────────

_PARAM_WIDGET_CLASSES: dict[NodeParamType, type[ParamWidgetBase]] = {
    NodeParamType.FILE_PATH: FilePathParamWidget,
    NodeParamType.INT:       IntParamWidget,
    NodeParamType.BOOL:      BoolParamWidget,
}


def build_param_widget(node: NodeBase, param: NodeParam) -> ParamWidgetBase | None:
    """Return a :class:`ParamWidgetBase` that edits *param* on *node*.

    Returns ``None`` for unsupported param types, so callers can render a
    placeholder label instead of crashing.
    """
    cls = _PARAM_WIDGET_CLASSES.get(param.param_type)
    if cls is None:
        logger.warning("No widget class registered for param type %s", param.param_type)
        return None
    return cls(node, param)

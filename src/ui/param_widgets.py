from __future__ import annotations

import logging
from enum import Enum
from pathlib import Path

from typing_extensions import override

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
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
from ui.controls.scene_aware_combobox import SceneAwareComboBox
from ui.icons import material_icon

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


class EnumParamWidget(ParamWidgetBase):
    """Combo-box editor for :attr:`NodeParamType.ENUM` parameters.

    The param's ``metadata["enum"]`` must hold the :class:`enum.Enum`
    subclass whose members are the legal values.  The combo lists every
    member (in declaration order) using its ``name`` formatted for
    readability (``FLOYD_STEINBERG`` → ``Floyd Steinberg``).  Selection
    writes the enum *member* back to the node; value round-trips through
    the setter even if the node stores it as an int internally (works
    seamlessly for :class:`enum.IntEnum`).
    """

    def __init__(self, node: NodeBase, param: NodeParam) -> None:
        super().__init__(node, param)
        enum_cls = param.metadata.get("enum")
        if not (isinstance(enum_cls, type) and issubclass(enum_cls, Enum)):
            raise ValueError(
                f"NodeParam {param.name!r}: ENUM params require "
                f"metadata['enum'] to be an Enum subclass "
                f"(got {enum_cls!r})."
            )
        self._enum_cls: type[Enum] = enum_cls

        self._combo = SceneAwareComboBox()
        self._combo.setMinimumWidth(96)
        for member in self._enum_cls:
            self._combo.addItem(self._label_for(member), member)

        initial = self._coerce(self._initial_value(next(iter(self._enum_cls))))
        idx = self._combo.findData(initial)
        if idx >= 0:
            self._combo.setCurrentIndex(idx)
        # Connect after the initial setCurrentIndex so we don't echo the
        # initial value back to the node via the setter (and fire a
        # spurious param_changed).
        self._combo.currentIndexChanged.connect(self._on_index_changed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._combo)

    def _on_index_changed(self, _index: int) -> None:
        member = self._combo.currentData()
        if member is None:
            return
        self._write_to_node(member)
        self.value_changed.emit(member)

    @override
    def set_value(self, value: object) -> None:
        member = self._coerce(value)
        idx = self._combo.findData(member)
        if idx >= 0:
            self._combo.setCurrentIndex(idx)

    @override
    def get_value(self) -> object:
        return self._combo.currentData()

    # ── Helpers ────────────────────────────────────────────────────────────

    def _coerce(self, value: object) -> Enum:
        """Return *value* as an instance of ``self._enum_cls``.

        Accepts the enum member itself, its ``value`` (int/str), or its
        ``name``. Falls back to the first declared member on failure so
        the combo always has a defined current row.
        """
        if isinstance(value, self._enum_cls):
            return value
        try:
            return self._enum_cls(value)
        except (ValueError, KeyError):
            pass
        if isinstance(value, str):
            try:
                return self._enum_cls[value]
            except KeyError:
                pass
        return next(iter(self._enum_cls))

    @staticmethod
    def _label_for(member: Enum) -> str:
        """Humanise an enum member's ``SHOUTY_SNAKE`` name for display."""
        return member.name.replace("_", " ").title()


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

        browse = QPushButton("...")
        browse.setFixedWidth(36)
        browse.clicked.connect(self._browse)

        self._view = QPushButton()
        self._view.setIcon(material_icon("visibility"))
        self._view.setFixedWidth(36)
        self._view.setToolTip("Open in system image viewer")
        self._view.clicked.connect(self._open_in_viewer)

        # Connect textChanged and seed the initial value only once
        # self._view exists, since _update_view_enabled touches it.
        self._line.textChanged.connect(self._on_value_changed)
        self._line.textChanged.connect(self._update_view_enabled)
        self._line.setText(str(self._initial_value("")))
        self._update_view_enabled()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self._line, 1)
        layout.addWidget(browse, 0)
        layout.addWidget(self._view, 0)

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
        fallback = OUTPUT_DIR if self._is_save else INPUT_DIR
        # Relative values (e.g. "out.png" or "example.jpg") are stored
        # relative to OUTPUT_DIR / INPUT_DIR, so resolve against that base
        # before taking the parent — otherwise the dialog would open in
        # the process CWD instead of the folder the file actually lives in.
        path_obj = Path(current)
        if not path_obj.is_absolute():
            path_obj = fallback / path_obj
        folder = path_obj.parent.resolve()
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
            # Run the value through the node setter (which may normalise it
            # — e.g. ImageSource shortens paths inside INPUT_DIR) and then
            # mirror the canonical form into the line edit so the user sees
            # what is actually stored. blockSignals avoids re-triggering the
            # textChanged → setter loop with the already-normalised value.
            self._write_to_node(path)
            canonical = str(getattr(self._node, self._param.name, path))
            self._line.blockSignals(True)
            try:
                self._line.setText(canonical)
            finally:
                self._line.blockSignals(False)
            self._update_view_enabled()
            self.value_changed.emit(canonical)

    def _resolved_current_path(self) -> Path:
        """Return the absolute path referenced by the line edit.

        Relative values are joined with ``OUTPUT_DIR`` / ``INPUT_DIR``
        to match how the corresponding node setters resolve them.
        """
        base = OUTPUT_DIR if self._is_save else INPUT_DIR
        p = Path(self._line.text() or "")
        if not p.is_absolute():
            p = base / p
        return p

    def _update_view_enabled(self) -> None:
        self._view.setEnabled(self._resolved_current_path().is_file())

    def _open_in_viewer(self) -> None:
        path = self._resolved_current_path()
        if path.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


# ── Registry & factory ─────────────────────────────────────────────────────────

_PARAM_WIDGET_CLASSES: dict[NodeParamType, type[ParamWidgetBase]] = {
    NodeParamType.FILE_PATH: FilePathParamWidget,
    NodeParamType.INT:       IntParamWidget,
    NodeParamType.BOOL:      BoolParamWidget,
    NodeParamType.ENUM:      EnumParamWidget,
}


def build_param_widget(node: NodeBase, param: NodeParam) -> ParamWidgetBase | None:
    """Return a :class:`ParamWidgetBase` that edits *param* on *node*.

    Returns ``None`` for unsupported param types, so callers can render a
    placeholder label instead of crashing.  Also returns ``None`` (with
    a log) when a widget constructor raises — misconfigured metadata
    should not bring the node editor down.
    """
    cls = _PARAM_WIDGET_CLASSES.get(param.param_type)
    if cls is None:
        logger.warning("No widget class registered for param type %s", param.param_type)
        return None
    try:
        return cls(node, param)
    except Exception:
        logger.exception(
            "Failed to build %s widget for %s.%s",
            cls.__name__, type(node).__name__, param.name,
        )
        return None

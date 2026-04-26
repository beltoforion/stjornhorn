from __future__ import annotations

import logging
from enum import Enum
from pathlib import Path

from typing_extensions import override

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDoubleSpinBox,
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

    def refresh(self) -> None:
        """Re-evaluate any state that depends on external conditions.

        Default is a no-op. Widgets whose enabled state depends on
        things the Qt signal machinery doesn't track — e.g. whether a
        file on disk exists — override this so the host page can ask
        every param widget to re-check after events like a flow run.
        """

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


class FloatParamWidget(ParamWidgetBase):
    """Double-spin-box editor for :attr:`NodeParamType.FLOAT` parameters.

    Supports optional ``metadata`` keys ``min``, ``max``, ``step`` and
    ``decimals`` to tune the spin box; unspecified keys fall back to a
    wide default range so arbitrary floats round-trip without clipping.
    """

    def __init__(self, node: NodeBase, param: NodeParam) -> None:
        super().__init__(node, param)
        self._spin = QDoubleSpinBox()
        meta = param.metadata
        self._spin.setRange(
            float(meta.get("min", -1e12)),
            float(meta.get("max",  1e12)),
        )
        self._spin.setDecimals(int(meta.get("decimals", 3)))
        self._spin.setSingleStep(float(meta.get("step", 0.1)))
        self._spin.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._spin.setMinimumWidth(96)
        self._spin.valueChanged.connect(self._on_value_changed)
        self._spin.setValue(float(self._initial_value(0.0)))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._spin)

    def _on_value_changed(self, value: float) -> None:
        self._write_to_node(value)
        self.value_changed.emit(value)

    @override
    def set_value(self, value: object) -> None:
        self._spin.setValue(float(value))

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


class StringParamWidget(ParamWidgetBase):
    """Line-edit editor for :attr:`NodeParamType.STRING` parameters.

    Commits on ``editingFinished`` (Enter or focus loss) rather than on
    every keystroke so a node setter that validates non-empty / bounded
    inputs doesn't raise while the user is still typing.

    Optional ``metadata`` keys:
      * ``placeholder`` — placeholder text shown when the line is empty.
      * ``max_length``  — hard character cap enforced by the widget.
    """

    def __init__(self, node: NodeBase, param: NodeParam) -> None:
        super().__init__(node, param)
        meta = param.metadata

        self._line = QLineEdit()
        self._line.setMinimumWidth(96)
        placeholder = meta.get("placeholder")
        if placeholder is not None:
            self._line.setPlaceholderText(str(placeholder))
        max_length = meta.get("max_length")
        if max_length is not None:
            self._line.setMaxLength(int(max_length))

        self._line.setText(str(self._initial_value("")))
        self._line.editingFinished.connect(self._on_editing_finished)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._line)

    def _on_editing_finished(self) -> None:
        value = self._line.text()
        self._write_to_node(value)
        # If the setter normalised the value (e.g. trimmed whitespace or
        # rejected empty and kept the previous) mirror the canonical form
        # back into the line edit so the user sees what's actually stored.
        canonical = getattr(self._node, self._param.name, value)
        if canonical != value:
            self._line.blockSignals(True)
            try:
                self._line.setText(str(canonical))
            finally:
                self._line.blockSignals(False)
        self.value_changed.emit(canonical)

    @override
    def set_value(self, value: object) -> None:
        self._line.setText(str(value))

    @override
    def get_value(self) -> object:
        return self._line.text()


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
        mode = param.metadata.get("mode")
        self._is_save      = mode == "save"
        self._is_directory = mode == "directory"
        self._filter = str(param.metadata.get("filter", ""))
        self._base_dir = Path(
            param.metadata.get("base_dir", OUTPUT_DIR if self._is_save else INPUT_DIR)
        ).resolve()

        self._line = QLineEdit()
        self._line.setPlaceholderText("Select a file…")
        # Min width must leave room for the 28 px browse button + spacing
        # inside the fixed-width node body, otherwise the line edit overflows
        # and visually overlaps the button.
        self._line.setMinimumWidth(80)

        browse = QPushButton("...")
        browse.setFixedWidth(36)
        browse.clicked.connect(self._open_file_dialog)

        self._view = QPushButton()
        self._view.setIcon(material_icon("visibility"))
        self._view.setFixedWidth(36)
        self._view.setToolTip("Open in system image viewer")
        self._view.clicked.connect(self._open_in_viewer)

        # Connect textChanged and seed the initial value only once
        # self._view exists, since _update_view_enabled touches it.
        self._line.textChanged.connect(self._on_value_changed)
        self._line.textChanged.connect(self._update_view_enabled)

        # initialize self._path and the line edit's text to the node's current value (or the
        self.set_value(str(self._initial_value(""))) 
        self._update_view_enabled()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self._line, 1)
        layout.addWidget(browse, 0)
        layout.addWidget(self._view, 0)

    def _on_value_changed(self, value: str) -> None:
        self._write_to_node(self._path)
        self.value_changed.emit(value)

    @override
    def set_value(self, value: object) -> None:
        text = str(value)
        if not text:
            self._path = Path()
            self._line.setText("")
            return

        # Relative inputs are resolved against base_dir (matching the
        # node setters), not the process CWD.
        raw = Path(text)
        new_path = (raw if raw.is_absolute() else self._base_dir / raw).resolve()

        # Paths that live under base_dir are displayed as relative, so
        # saved flows stay portable across machines with different
        # absolute layouts.
        if new_path.is_relative_to(self._base_dir):
            display = new_path.relative_to(self._base_dir).as_posix()
        else:
            display = new_path.as_posix()

        # Assign _path before setText so the textChanged slots
        # (_update_view_enabled in particular) see a valid path.
        self._path = new_path
        self._line.setText(display)

    @override
    def get_value(self) -> object:
        return self._line.text()

    def _open_file_dialog(self) -> None:
        current = self._line.text() or ""
        # Relative values (e.g. "out.png" or "example.jpg") are stored
        # relative to the node's base_dir, so resolve against that base
        # before taking the parent — otherwise the dialog would open in
        # the process CWD instead of the folder the file actually lives in.
        path_obj = Path(current)
        if not path_obj.is_absolute():
            path_obj = self._base_dir / path_obj
        folder = path_obj.parent.resolve()
        initial = str(folder) if folder.is_dir() else str(self._base_dir)

        if self._is_directory:
            default_caption = "Select Folder"
        elif self._is_save:
            default_caption = "Save File As"
        else:
            default_caption = "Select File"
        caption = self._param.metadata.get("caption", default_caption)

        dialog = QFileDialog(QApplication.activeWindow(), caption)
        dialog.setDirectory(initial)

        if self._is_directory:
            dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
            dialog.setFileMode(QFileDialog.FileMode.Directory)
            dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
        elif self._is_save:
            dialog.setNameFilter(self._filter)
            dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        else:
            dialog.setNameFilter(self._filter)
            dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
            dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        
        dialog.show()
        top = QApplication.activeWindow()
        geo = dialog.frameGeometry()
        geo.moveCenter(top.frameGeometry().center())
        dialog.move(geo.topLeft())

        if dialog.exec() != QFileDialog.DialogCode.Accepted:
            return

        files = dialog.selectedFiles()
        path = files[0] if files else ""

        if path:
            self._line.blockSignals(True)
            try:
                self.set_value(path) 
            finally:
                self._line.blockSignals(False)

            self._write_to_node(path)
            self._update_view_enabled()

    def _update_view_enabled(self) -> None:
        # In directory mode the view button opens the folder in the OS
        # file manager, so enable it whenever the path is a real dir;
        # otherwise it opens the file in a viewer, so we want is_file().
        ok = self._path.is_dir() if self._is_directory else self._path.is_file()
        self._view.setEnabled(ok)

    @override
    def refresh(self) -> None:
        # The view button's enabled state depends on whether the file
        # exists on disk — something a flow run can change. Re-check so
        # sinks that just wrote their output light up without the user
        # having to edit the path.
        self._update_view_enabled()

    def _open_in_viewer(self) -> None:
        # QDesktopServices.openUrl on a directory opens the OS file
        # manager at that path, so the same call works for both modes.
        target = self._path
        ok = target.is_dir() if self._is_directory else target.is_file()
        if ok:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))


# ── Registry & factory ─────────────────────────────────────────────────────────

_PARAM_WIDGET_CLASSES: dict[NodeParamType, type[ParamWidgetBase]] = {
    NodeParamType.FILE_PATH: FilePathParamWidget,
    NodeParamType.INT:       IntParamWidget,
    NodeParamType.FLOAT:     FloatParamWidget,
    NodeParamType.BOOL:      BoolParamWidget,
    NodeParamType.ENUM:      EnumParamWidget,
    NodeParamType.STRING:    StringParamWidget,
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

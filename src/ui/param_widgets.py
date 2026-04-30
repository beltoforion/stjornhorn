from __future__ import annotations

import logging
from enum import Enum
from pathlib import Path

from typing_extensions import override

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QValidator
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QWidget,
)

from constants import INPUT_DIR, OUTPUT_DIR
from core.filename_template import expand as expand_template
from core.io_data import IoDataType
from core.node_base import NodeBase, NodeParamType
from core.port import InputPort
from ui.controls.scene_aware_combobox import SceneAwareComboBox
from ui.icons import material_icon

logger = logging.getLogger(__name__)


#: Minimum width for the value-bearing control on a single-element
#: param widget (QSpinBox / QDoubleSpinBox / QLineEdit / QComboBox).
#: Sized so the up/down arrow column doesn't crowd the visible
#: digits / first character of text. Below ~80 the spin buttons start
#: clipping the value; above ~100 a row in a narrow node wastes
#: horizontal space the label could otherwise use.
PARAM_VALUE_MIN_WIDTH: int = 96

#: Minimum width for a path-style line edit (FilePathParamWidget).
#: Smaller than the numeric min because the widget sits next to two
#: buttons on the same row and fights for horizontal real estate.
PATH_LINE_EDIT_MIN_WIDTH: int = 80

#: Width of an icon-only button on a multi-element param widget
#: (FilePathParamWidget's "..." Browse and visibility "View" buttons).
#: Big enough for the material icon glyph + a few px of padding,
#: small enough that two of them don't dominate the row.
PARAM_BUTTON_WIDTH: int = 36

#: Fixed height for every value-bearing control on a param widget.
#: Locks the size at a compact, Blender-style 22 px regardless of OS
#: style — without this Qt picks ``sizeHint().height()`` which on
#: native styles ranges from ~22 (Fusion) to ~28 (Windows-Vista,
#: macOS), making the same node look too tall on some machines and
#: visually inconsistent across rows when widget kinds disagree on
#: their natural height. 22 px fits a 14-px font + 4 px of vertical
#: padding (matches the QSS ``padding: 3px 6px``) + 2 px of border.
PARAM_VALUE_HEIGHT: int = 24


#: Tooltip shown on hover over a :class:`FilePathParamWidget`'s line
#: edit. Lists the ``$token$`` placeholders the
#: :mod:`core.filename_template` engine resolves, with a one-line
#: example, so the user has a just-in-time cheat sheet without having
#: to leave the editor.
_PATH_TEMPLATE_TOOLTIP: str = (
    "Path or filename template.\n"
    "\n"
    "Available $token$ placeholders:\n"
    "  $frame_index$   per-port emit counter (0, 1, 2, …)\n"
    "  $source_stem$   input filename, no extension  (e.g. 'photo')\n"
    "  $source_name$   input filename, with extension ('photo.jpg')\n"
    "  $source_ext$    input extension, no dot       ('jpg')\n"
    "  $flow_name$     name of the loaded flow\n"
    "  $<port_name>$   value of a connected SCALAR input\n"
    "                   (e.g. '$tick$' for a wired tick port)\n"
    "\n"
    "Width syntax: $token:N$ zero-pads numerics to N digits.\n"
    "\n"
    'Example: "$frame_index:4$_$source_stem$.$source_ext$"\n'
    "       → 0042_photo.jpg\n"
    "\n"
    "A literal path with no placeholders is overwritten on every\n"
    "frame — same as the legacy single-write behaviour."
)


class ParamWidgetBase(QWidget):
    """Base class for all parameter editor widgets embedded in a NodeItem.

    Each subclass binds to a single :class:`InputPort` (a
    "param-style" input — one whose metadata carries a
    ``"param_type"`` key) on a :class:`NodeBase` instance and exposes
    a uniform :meth:`set_value` / :meth:`get_value` interface so
    callers can refresh or read widget state without knowing the
    concrete type.
    """

    #: Emitted after any user interaction that commits a new value.
    value_changed = Signal(object)

    def __init__(self, node: NodeBase, port: InputPort) -> None:
        if type(self) is ParamWidgetBase:
            raise TypeError("ParamWidgetBase cannot be instantiated directly")
        super().__init__()
        self._node = node
        self._port = port
        # The wrapper hosts the QHBoxLayout that carries the
        # value-bearing control(s). Without explicit transparency it
        # inherits the global ``QWidget { background: #262629 }`` rule
        # and paints a dark grey strip behind every child — most
        # visible behind a QCheckBox (a 14-px box on a ~24-px-tall
        # row leaves background showing on three sides).
        # ``WA_TranslucentBackground`` is enough by itself; using
        # ``setStyleSheet`` here would propagate to children and strip
        # the QSpinBox / QLineEdit / etc. of their dark
        # ``#1f1f22`` input-field fill.
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

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

    def _make_row_layout(self, spacing: int = 0) -> QHBoxLayout:
        """Install a zero-margin :class:`QHBoxLayout` on this widget and
        return it so the caller can attach value-bearing controls.

        Every concrete param widget hosts its controls in a horizontal
        row with no contents margins (so the row sits flush against the
        node body's parameter slot). Centralising the boilerplate keeps
        all widgets visually consistent and shrinks each subclass.
        """
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(spacing)
        return layout

    @staticmethod
    def _size_value_control(control: QWidget) -> None:
        """Apply the standard min-width / fixed-height to a value control.

        See :data:`PARAM_VALUE_MIN_WIDTH` and :data:`PARAM_VALUE_HEIGHT`
        for the rationale on the chosen pixel values. Used by every
        single-control numeric / string / enum widget; FilePath sizes
        its line edit separately because it shares the row with two
        buttons.
        """
        control.setMinimumWidth(PARAM_VALUE_MIN_WIDTH)
        control.setFixedHeight(PARAM_VALUE_HEIGHT)

    def _initial_value(self, fallback: object) -> object:
        """Return the value the widget should display on first creation.

        Prefers the node's current attribute (so loaded flows show their
        saved values) and falls back to the metadata default (so
        freshly-instantiated nodes still get the right starting text even if
        the subclass forgot :meth:`NodeBase._apply_default_params`).
        """
        if hasattr(self._node, self._port.name):
            return getattr(self._node, self._port.name)
        return self._port.metadata.get("default", fallback)

    def _write_to_node(self, value: object) -> None:
        """Write *value* to the node attribute, logging any error."""
        try:
            setattr(self._node, self._port.name, value)
        except Exception:
            logger.exception(
                "Failed to set %s.%s = %r",
                type(self._node).__name__, self._port.name, value,
            )


# ── Concrete widgets ───────────────────────────────────────────────────────────

class IntParamWidget(ParamWidgetBase):
    """Spin-box editor for :attr:`NodeParamType.INT` parameters."""

    def __init__(self, node: NodeBase, port: InputPort) -> None:
        super().__init__(node, port)
        self._spin = self._build_spin_box(port)
        self._spin.setRange(-10_000_000, 10_000_000)
        self._spin.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._size_value_control(self._spin)
        self._spin.valueChanged.connect(self._on_value_changed)
        self._spin.setValue(int(self._initial_value(0)))
        self._make_row_layout().addWidget(self._spin)

    def _build_spin_box(self, port: InputPort) -> QSpinBox:
        """Hook for subclasses to inject a custom :class:`QSpinBox`.

        Default returns a plain :class:`QSpinBox`; :class:`OddIntParamWidget`
        overrides it to return an :class:`_OddSpinBox` so the validate /
        fixup / step-by-2 behaviour piggybacks on the rest of the
        construction sequence (range, alignment, size, signal wire-up,
        initial value) without duplication.
        """
        return QSpinBox()

    def _on_value_changed(self, value: int) -> None:
        self._write_to_node(value)
        self.value_changed.emit(value)

    @override
    def set_value(self, value: object) -> None:
        self._spin.setValue(int(value))

    @override
    def get_value(self) -> object:
        return self._spin.value()


class _OddSpinBox(QSpinBox):
    """:class:`QSpinBox` constrained to odd integers.

    Steps in twos so the up/down arrows skip over even values, marks
    a typed even number as :attr:`QValidator.State.Intermediate` (so
    the user can keep typing without the box snapping back), and
    fixes any committed even value up to the next odd integer on
    :meth:`fixup`. Mirrors the descriptor's
    :meth:`OddIntParam._shape` rule one layer up so what the user
    sees in the spin box matches what the node stores.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSingleStep(2)

    @override
    def validate(self, input_: str, pos: int) -> tuple[QValidator.State, str, int]:
        state, text, new_pos = super().validate(input_, pos)
        if state != QValidator.State.Acceptable:
            return state, text, new_pos
        try:
            value = int(text)
        except ValueError:
            return state, text, new_pos
        if value % 2 == 0:
            return QValidator.State.Intermediate, text, new_pos
        return state, text, new_pos

    @override
    def fixup(self, input_: str) -> str:
        try:
            value = int(input_)
        except ValueError:
            return super().fixup(input_)
        if value % 2 == 0:
            return str(value + 1)
        return input_


class OddIntParamWidget(IntParamWidget):
    """Spin-box editor for :class:`~core.params.OddIntParam`.

    Swaps the base :class:`QSpinBox` for :class:`_OddSpinBox` so the
    widget enforces the odd-only invariant the descriptor declares.
    Issue: #259
    """

    @override
    def _build_spin_box(self, port: InputPort) -> QSpinBox:
        return _OddSpinBox()


class FloatParamWidget(ParamWidgetBase):
    """Double-spin-box editor for :attr:`NodeParamType.FLOAT` parameters.

    Supports optional ``metadata`` keys ``min``, ``max``, ``step`` and
    ``decimals`` to tune the spin box; unspecified keys fall back to a
    wide default range so arbitrary floats round-trip without clipping.
    """

    def __init__(self, node: NodeBase, port: InputPort) -> None:
        super().__init__(node, port)
        self._spin = QDoubleSpinBox()
        meta = port.metadata
        self._spin.setRange(
            float(meta.get("min", -1e12)),
            float(meta.get("max",  1e12)),
        )
        self._spin.setDecimals(int(meta.get("decimals", 3)))
        self._spin.setSingleStep(float(meta.get("step", 0.1)))
        self._spin.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._size_value_control(self._spin)
        self._spin.valueChanged.connect(self._on_value_changed)
        self._spin.setValue(float(self._initial_value(0.0)))
        self._make_row_layout().addWidget(self._spin)

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

    def __init__(self, node: NodeBase, port: InputPort) -> None:
        super().__init__(node, port)
        self._check = QCheckBox()
        self._check.toggled.connect(self._on_value_changed)
        self._check.setChecked(bool(self._initial_value(False)))
        self._make_row_layout().addWidget(self._check)

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

    def __init__(self, node: NodeBase, port: InputPort) -> None:
        super().__init__(node, port)
        meta = port.metadata

        self._line = QLineEdit()
        self._size_value_control(self._line)
        placeholder = meta.get("placeholder")
        if placeholder is not None:
            self._line.setPlaceholderText(str(placeholder))
        max_length = meta.get("max_length")
        if max_length is not None:
            self._line.setMaxLength(int(max_length))

        self._line.setText(str(self._initial_value("")))
        self._line.editingFinished.connect(self._on_editing_finished)
        self._make_row_layout().addWidget(self._line)

    def _on_editing_finished(self) -> None:
        value = self._line.text()
        self._write_to_node(value)
        # If the setter normalised the value (e.g. trimmed whitespace or
        # rejected empty and kept the previous) mirror the canonical form
        # back into the line edit so the user sees what's actually stored.
        canonical = getattr(self._node, self._port.name, value)
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

    def __init__(self, node: NodeBase, port: InputPort) -> None:
        super().__init__(node, port)
        enum_cls = port.metadata.get("enum")
        if not (isinstance(enum_cls, type) and issubclass(enum_cls, Enum)):
            raise ValueError(
                f"Port {port.name!r}: ENUM params require "
                f"metadata['enum'] to be an Enum subclass "
                f"(got {enum_cls!r})."
            )
        self._enum_cls: type[Enum] = enum_cls

        self._combo = SceneAwareComboBox()
        self._size_value_control(self._combo)
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
        self._make_row_layout().addWidget(self._combo)

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


class _TemplatePreviewPopup(QFrame):
    """Floating tooltip-style frame that previews a rendered filename
    template below an anchor :class:`QLineEdit`.

    Top-level (parented to the anchor only for ownership / lifetime;
    the window flag combination keeps it floating, frameless, and
    non-stealing-of-focus) so showing it never disturbs the
    fixed-row :class:`~ui.node_item.NodeItem` layout — the alternative
    of an inline label below the line edit overlaps the next
    parameter row when the row height is fixed at
    :data:`~ui.param_widgets.PARAM_VALUE_HEIGHT`.

    The anchor stays the source of truth for positioning: every
    :meth:`show_preview` call recomputes the screen position from the
    line edit's current global geometry, so dragging the node or
    scrolling the editor keeps the preview glued to its source.
    """

    def __init__(self, anchor: QLineEdit) -> None:
        super().__init__(
            anchor,
            Qt.WindowType.ToolTip
            | Qt.WindowType.FramelessWindowHint,
        )
        self._anchor = anchor
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setStyleSheet(
            "QFrame { background: #2f2f33; border: 1px solid #1a1a1d;"
            "         border-radius: 3px; }"
            "QLabel { color: #d6d6d6; font-size: 11px;"
            "         font-family: 'Consolas','Menlo',monospace;"
            "         padding: 4px 6px; }"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._label = QLabel()
        layout.addWidget(self._label)

    def show_preview(self, text: str) -> None:
        """Update the previewed text and surface the popup just below
        the anchor's bottom-left corner."""
        self._label.setText(text)
        self.adjustSize()
        anchor_bottom_left = self._anchor.mapToGlobal(
            self._anchor.rect().bottomLeft()
        )
        # 2 px gap so the popup doesn't touch the line-edit border.
        self.move(anchor_bottom_left.x(), anchor_bottom_left.y() + 2)
        self.show()


class FilePathParamWidget(ParamWidgetBase):
    """Line-edit + browse-button editor for :attr:`NodeParamType.FILE_PATH` parameters."""

    def __init__(self, node: NodeBase, port: InputPort) -> None:
        super().__init__(node, port)
        mode = port.metadata.get("mode")
        self._is_save      = mode == "save"
        self._is_directory = mode == "directory"
        self._filter = str(port.metadata.get("filter", ""))
        self._base_dir = Path(
            port.metadata.get("base_dir", OUTPUT_DIR if self._is_save else INPUT_DIR)
        ).resolve()

        self._line = QLineEdit()
        self._line.setPlaceholderText("Select a file…")
        # Min width must leave room for the 28 px browse button + spacing
        # inside the fixed-width node body, otherwise the line edit overflows
        # and visually overlaps the button.
        self._line.setMinimumWidth(PATH_LINE_EDIT_MIN_WIDTH)
        self._line.setFixedHeight(PARAM_VALUE_HEIGHT)
        # Reference card on hover. The param's own ``description`` is
        # also shown by the doc panel; this tooltip is the just-in-time
        # cheat sheet for the ``$token$`` syntax so users don't have to
        # leave the editor.
        self._line.setToolTip(_PATH_TEMPLATE_TOOLTIP)

        browse = QPushButton("...")
        browse.setFixedWidth(PARAM_BUTTON_WIDTH)
        browse.setFixedHeight(PARAM_VALUE_HEIGHT)
        browse.clicked.connect(self._open_file_dialog)

        self._view = QPushButton()
        self._view.setIcon(material_icon("visibility"))
        self._view.setFixedWidth(PARAM_BUTTON_WIDTH)
        self._view.setFixedHeight(PARAM_VALUE_HEIGHT)
        self._view.setToolTip("Open in system image viewer")
        self._view.clicked.connect(self._open_in_viewer)

        # Live preview popup for rendered templates. Floats below the
        # line edit as a separate top-level QFrame so the existing
        # NodeItem row layout (fixed-height rows in
        # ``_layout_param_widgets``) doesn't have to grow when a
        # template appears. Hidden by default; shown when the field
        # contains a ``$``-token, hidden again when the user clears
        # all tokens or focus leaves the field.
        self._preview_popup = _TemplatePreviewPopup(self._line)

        # Connect textChanged and seed the initial value only once
        # self._view + self._preview_popup exist, since both update
        # slots touch them.
        self._line.textChanged.connect(self._on_value_changed)
        self._line.textChanged.connect(self._update_view_enabled)
        self._line.textChanged.connect(self._update_preview)
        self._line.editingFinished.connect(self._preview_popup.hide)

        # initialize self._path and the line edit's text to the node's current value (or the
        self.set_value(str(self._initial_value("")))
        self._update_view_enabled()

        layout = self._make_row_layout(spacing=4)
        layout.addWidget(self._line, 1)
        layout.addWidget(browse, 0)
        layout.addWidget(self._view, 0)

    def _on_value_changed(self, value: str) -> None:
        # Mirror the typed value into ``self._path`` so the
        # ``_update_view_enabled`` slot (which also fires on
        # textChanged) sees the same path the user just typed —
        # otherwise it'd read a stale value seeded by the last
        # ``set_value`` call. ``set_value`` is *not* called here
        # because it would call ``setText`` and recurse through
        # textChanged.
        if not value:
            self._path = Path()
        else:
            raw = Path(value)
            self._path = raw if raw.is_absolute() else self._base_dir / raw
        # Write the raw typed text to the node — the FilePathParam
        # descriptor's ``_coerce`` runs ``store_relative_to`` so the
        # path is stored portably (relative to base_dir when
        # applicable), and templates like ``$frame_index$.png`` —
        # which aren't real filesystem paths — pass through
        # unchanged because ``store_relative_to`` skips relative
        # values.
        self._write_to_node(value)
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
        caption = self._port.metadata.get("caption", default_caption)

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

    def _update_preview(self, text: str) -> None:
        """Render *text* against a synthetic meta + scalar-port context
        and surface the result in the floating preview popup.

        Hidden when the field contains no ``$`` so a literal-path user
        doesn't see noise. Visible the moment a token appears, with
        the rendered example so a typo (``$source_stm$``) shows up
        immediately as a left-over literal placeholder.
        """
        if "$" not in text:
            self._preview_popup.hide()
            return

        meta: dict[str, object] = {
            "source_path": Path("example/photo.jpg"),
            "frame_index": 0,
            "timestamp": 1700000000.0,
        }
        # Each declared SCALAR input on the node contributes its port
        # name as a context token with a sample value 1, so a ``tick``
        # port wired to a ``RangeSource`` previews ``$tick$`` → 1 even
        # before the flow runs.
        context: dict[str, object] = {"flow_name": "demo"}
        for port in self._node.inputs:
            if IoDataType.SCALAR in port.accepted_types:
                context.setdefault(port.name, 1)

        rendered = expand_template(text, meta, context)
        self._preview_popup.show_preview(f"→ {rendered}")

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

#: Per-shape widget overrides keyed by the ``widget_kind`` string a
#: descriptor advertises in its metadata. Consulted before the
#: per-:class:`NodeParamType` dispatch so a shape-specific descriptor
#: (e.g. :class:`~core.params.OddIntParam`) can pick a custom widget
#: without growing :data:`_PARAM_WIDGET_CLASSES` — every entry there
#: would otherwise need to consider every shape.
_PARAM_WIDGET_BY_KIND: dict[str, type[ParamWidgetBase]] = {
    "odd_int": OddIntParamWidget,
}


def _install_description_tooltip(
    widget: ParamWidgetBase,
    port: InputPort,
) -> None:
    """Apply the port's metadata ``"description"`` as a tooltip.

    Qt looks tooltips up on the leaf widget under the cursor and does
    not walk the parent chain, so setting the tooltip only on the
    wrapper :class:`ParamWidgetBase` would never fire when the user
    hovers the embedded :class:`QSpinBox` or :class:`QLineEdit`. We
    therefore propagate the description to every ``QWidget`` descendant
    found via :meth:`findChildren`, which keeps every existing widget
    subclass — and any future ones — covered without per-class
    bookkeeping.

    Children that already carry an explicit, more-specific tooltip
    (e.g. the eye-icon button in :class:`FilePathParamWidget` saying
    "Open in system image viewer") are left untouched: the
    description complements those, not replaces them.
    """
    desc = port.metadata.get("description")
    if not desc:
        return
    widget.setToolTip(desc)
    for child in widget.findChildren(QWidget):
        if not child.toolTip():
            child.setToolTip(desc)


def build_param_widget(node: NodeBase, port: InputPort) -> ParamWidgetBase | None:
    """Return a :class:`ParamWidgetBase` that edits *port* on *node*.

    Returns ``None`` for unsupported param types, so callers can render a
    placeholder label instead of crashing.  Also returns ``None`` (with
    a log) when a widget constructor raises — misconfigured metadata
    should not bring the node editor down.
    """
    widget_kind = port.metadata.get("widget_kind")
    param_type = port.metadata.get("param_type")
    cls = _PARAM_WIDGET_BY_KIND.get(widget_kind) if widget_kind else None
    if cls is None:
        cls = _PARAM_WIDGET_CLASSES.get(param_type)
    if cls is None:
        logger.warning(
            "No widget class registered for port %r "
            "(param_type=%r, widget_kind=%r)",
            port.name, param_type, widget_kind,
        )
        return None
    try:
        widget = cls(node, port)
    except Exception:
        logger.exception(
            "Failed to build %s widget for %s.%s",
            cls.__name__, type(node).__name__, port.name,
        )
        return None
    _install_description_tooltip(widget, port)
    return widget

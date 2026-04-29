"""Unit tests for the class-level :mod:`core.params` descriptors.

Locks down the H2 contract:
  * ``__set__`` runs ``_coerce`` then ``_validate`` then writes the
    instance's ``_<name>`` slot.
  * ``__get__`` returns the slot value via the public attribute.
  * Domain subclasses (e.g. :class:`OddIntParam`) extend ``_coerce`` and
    inherit ``__set__`` semantics unchanged.
  * :meth:`NodeBase.__init_subclass__` collects descriptors into
    ``cls._param_descriptors``.
  * :meth:`NodeBase._apply_default_params` auto-creates the matching
    :class:`InputPort` once per node instance, placed *after* the
    explicit inputs the subclass added (preserving image-first ordering).
"""
from __future__ import annotations

import pytest

from enum import IntEnum

from core.io_data import IMAGE_TYPES, IoDataType
from core.node_base import NodeBase
from core.params import (
    BoolParam,
    ClampedFloatParam,
    EnumParam,
    FilePathParam,
    FloatParam,
    IntParam,
    OddIntParam,
    StringParam,
)
from core.port import InputPort, OutputPort


class _DescriptorNode(NodeBase):
    """Minimal NodeBase subclass for descriptor mechanics tests."""

    count = IntParam(3, min=0, max=10, description="Item count")
    ratio = FloatParam(0.5, min=0.0, max=1.0, step=0.05, decimals=2)
    kernel = OddIntParam(5, min=1, unit="px")

    def __init__(self) -> None:
        super().__init__("Test Node", section="Tests")
        self._add_input(InputPort("image", set(IMAGE_TYPES)))
        self._add_output(OutputPort("image", set(IMAGE_TYPES)))
        self._apply_default_params()

    def process_impl(self) -> None:  # pragma: no cover (not exercised in tests)
        pass


# ── Descriptor mechanics ──────────────────────────────────────────────────────

def test_int_param_coerces_to_int() -> None:
    node = _DescriptorNode()
    node.count = 7.9  # float → int truncation
    assert node.count == 7
    assert isinstance(node.count, int)


def test_int_param_rejects_below_min() -> None:
    node = _DescriptorNode()
    with pytest.raises(ValueError, match=r"count must be >= 0"):
        node.count = -1


def test_int_param_rejects_above_max() -> None:
    node = _DescriptorNode()
    with pytest.raises(ValueError, match=r"count must be <= 10"):
        node.count = 11


def test_float_param_coerces_to_float() -> None:
    node = _DescriptorNode()
    node.ratio = 1  # int → float
    assert node.ratio == 1.0
    assert isinstance(node.ratio, float)


def test_float_param_range_check() -> None:
    node = _DescriptorNode()
    with pytest.raises(ValueError):
        node.ratio = 1.5


def test_odd_int_param_bumps_even_to_next_odd() -> None:
    node = _DescriptorNode()
    node.kernel = 6
    assert node.kernel == 7


def test_odd_int_param_leaves_odd_unchanged() -> None:
    node = _DescriptorNode()
    node.kernel = 9
    assert node.kernel == 9


def test_odd_int_param_below_min_raises_before_shaping() -> None:
    """The min gate applies to the type-coerced value, *before* the
    odd-only shape runs — so 0 raises rather than being silently
    bumped up to 1. Matches the behaviour of the hand-rolled setters
    this descriptor replaces.
    """
    node = _DescriptorNode()
    with pytest.raises(ValueError, match=r"kernel must be >= 1"):
        node.kernel = 0
    with pytest.raises(ValueError, match=r"kernel must be >= 1"):
        node.kernel = -2


# ── Defaults applied at construction ─────────────────────────────────────────

def test_defaults_set_at_construction() -> None:
    node = _DescriptorNode()
    assert node.count == 3
    assert node.ratio == 0.5
    assert node.kernel == 5


def test_private_slots_initialised_before_apply_default_params() -> None:
    """The private ``_<name>`` slot must exist immediately after
    ``super().__init__()`` so subclass code between super-init and
    ``_apply_default_params`` can read it without AttributeError.
    """
    # Construct a node and verify the slots exist on the instance.
    node = _DescriptorNode()
    assert hasattr(node, "_count")
    assert hasattr(node, "_ratio")
    assert hasattr(node, "_kernel")


# ── Class-level descriptor collection ────────────────────────────────────────

def test_init_subclass_collects_descriptors() -> None:
    descriptors = _DescriptorNode._param_descriptors
    names = {d.name for d in descriptors}
    assert names == {"count", "ratio", "kernel"}


def test_subclass_inherits_parent_descriptors() -> None:
    class _Child(_DescriptorNode):
        extra = IntParam(0)

        def process_impl(self) -> None: pass

    names = {d.name for d in _Child._param_descriptors}
    assert names == {"count", "ratio", "kernel", "extra"}


# ── Auto-port creation ───────────────────────────────────────────────────────

def test_descriptor_ports_appended_after_explicit_inputs() -> None:
    """Image input added explicitly first → image port stays at index 0."""
    node = _DescriptorNode()
    names = [p.name for p in node.inputs]
    assert names[0] == "image"
    assert set(names[1:]) == {"count", "ratio", "kernel"}


def test_descriptor_port_carries_metadata() -> None:
    node = _DescriptorNode()
    count_port = next(p for p in node.inputs if p.name == "count")
    assert count_port.metadata["min"] == 0
    assert count_port.metadata["max"] == 10
    assert count_port.metadata["default"] == 3
    assert count_port.metadata["description"] == "Item count"
    assert count_port.default_value == 3
    assert count_port.optional is True


def test_descriptor_port_uses_scalar_io_type() -> None:
    node = _DescriptorNode()
    count_port = next(p for p in node.inputs if p.name == "count")
    assert IoDataType.SCALAR in count_port.accepted_types


def test_existing_input_with_same_name_blocks_auto_creation() -> None:
    """A subclass that hand-rolls an InputPort with the same name as a
    descriptor wins — _apply_default_params skips the auto-creation."""

    class _MixedNode(NodeBase):
        count = IntParam(3, min=0)

        def __init__(self) -> None:
            super().__init__("Mixed", section="Tests")
            # Explicit hand-rolled port with the same name as the descriptor.
            self._add_input(InputPort(
                "count",
                {IoDataType.SCALAR},
                optional=True,
                default_value=99,
                metadata={"param_type": "INT", "default": 99, "explicit": True},
            ))
            self._add_output(OutputPort("image", set(IMAGE_TYPES)))
            self._apply_default_params()

        def process_impl(self) -> None: pass

    node = _MixedNode()
    count_ports = [p for p in node.inputs if p.name == "count"]
    assert len(count_ports) == 1
    assert count_ports[0].metadata.get("explicit") is True


# ── Bool / Enum / Clamped / exclusive bound ──────────────────────────────────

class _Mood(IntEnum):
    HAPPY = 1
    SAD   = 2
    BORED = 3


class _ExtraParamsNode(NodeBase):
    """Test node exercising BoolParam / EnumParam / ClampedFloatParam /
    FloatParam(min_exclusive=...)."""

    enabled = BoolParam(False, description="Toggle")
    mood = EnumParam(_Mood, _Mood.HAPPY, description="Vibe")
    opacity = ClampedFloatParam(0.5, min=0.0, max=1.0)
    factor = FloatParam(1.0, min=0.0, min_exclusive=True)

    def __init__(self) -> None:
        super().__init__("Extra", section="Tests")
        self._add_output(OutputPort("image", set(IMAGE_TYPES)))
        self._apply_default_params()

    def process_impl(self) -> None: pass


def test_bool_param_coerces_truthy_and_falsy() -> None:
    node = _ExtraParamsNode()
    node.enabled = 1
    assert node.enabled is True
    node.enabled = ""
    assert node.enabled is False


def test_bool_param_port_uses_bool_io_type() -> None:
    node = _ExtraParamsNode()
    port = next(p for p in node.inputs if p.name == "enabled")
    assert IoDataType.BOOL in port.accepted_types


def test_enum_param_accepts_member() -> None:
    node = _ExtraParamsNode()
    node.mood = _Mood.SAD
    assert node.mood is _Mood.SAD


def test_enum_param_accepts_int_value() -> None:
    node = _ExtraParamsNode()
    node.mood = 3
    assert node.mood is _Mood.BORED


def test_enum_param_accepts_name_string() -> None:
    node = _ExtraParamsNode()
    node.mood = "SAD"
    assert node.mood is _Mood.SAD


def test_enum_param_rejects_unknown_value() -> None:
    node = _ExtraParamsNode()
    with pytest.raises(ValueError):
        node.mood = 999


def test_enum_param_default_must_be_member() -> None:
    with pytest.raises(TypeError):
        EnumParam(_Mood, 1)  # int, not _Mood


def test_enum_param_metadata_carries_class() -> None:
    node = _ExtraParamsNode()
    port = next(p for p in node.inputs if p.name == "mood")
    assert port.metadata["enum"] is _Mood


def test_clamped_float_param_clamps_above_max() -> None:
    node = _ExtraParamsNode()
    node.opacity = 2.5
    assert node.opacity == 1.0


def test_clamped_float_param_clamps_below_min() -> None:
    node = _ExtraParamsNode()
    node.opacity = -0.3
    assert node.opacity == 0.0


def test_clamped_float_param_in_range_passes_through() -> None:
    node = _ExtraParamsNode()
    node.opacity = 0.7
    assert node.opacity == 0.7


def test_clamped_float_metadata_still_carries_bounds() -> None:
    """Widget needs min/max for the slider even though the descriptor
    enforces them via clamping rather than raising."""
    node = _ExtraParamsNode()
    port = next(p for p in node.inputs if p.name == "opacity")
    assert port.metadata["min"] == 0.0
    assert port.metadata["max"] == 1.0


def test_float_min_exclusive_rejects_boundary() -> None:
    """``min_exclusive=True`` makes the bound strict — value == min raises."""
    node = _ExtraParamsNode()
    with pytest.raises(ValueError, match=r"factor must be > 0"):
        node.factor = 0.0


def test_float_min_exclusive_accepts_just_above_boundary() -> None:
    node = _ExtraParamsNode()
    node.factor = 0.001
    assert node.factor == 0.001


# ── String / FilePath ────────────────────────────────────────────────────────

class _PathishNode(NodeBase):
    """Test node exercising StringParam / FilePathParam."""

    label = StringParam("hi", placeholder="Type a label", max_length=64)
    notes = StringParam("", description="Free-form notes")
    target = FilePathParam("out.png", mode="save", filter="PNG (*.png)")

    def __init__(self) -> None:
        super().__init__("Pathish", section="Tests")
        self._add_output(OutputPort("image", set(IMAGE_TYPES)))
        self._apply_default_params()

    def process_impl(self) -> None: pass


def test_string_param_coerces_to_str() -> None:
    node = _PathishNode()
    node.label = 42
    assert node.label == "42"
    assert isinstance(node.label, str)


def test_string_param_metadata_carries_placeholder_and_max_length() -> None:
    node = _PathishNode()
    port = next(p for p in node.inputs if p.name == "label")
    assert port.metadata["placeholder"] == "Type a label"
    assert port.metadata["max_length"] == 64


def test_string_param_uses_string_io_type() -> None:
    node = _PathishNode()
    port = next(p for p in node.inputs if p.name == "label")
    assert IoDataType.STRING in port.accepted_types


def test_filepath_param_metadata_carries_mode_and_filter() -> None:
    node = _PathishNode()
    port = next(p for p in node.inputs if p.name == "target")
    assert port.metadata["mode"] == "save"
    assert port.metadata["filter"] == "PNG (*.png)"


def test_filepath_param_uses_path_io_type() -> None:
    node = _PathishNode()
    port = next(p for p in node.inputs if p.name == "target")
    assert IoDataType.PATH in port.accepted_types


def test_filepath_param_default_open_mode_omits_metadata_key() -> None:
    """Default mode (``"open"``) is not emitted into metadata to keep
    saved-flow representations small."""

    class _OpenNode(NodeBase):
        path = FilePathParam("a.png")

        def __init__(self) -> None:
            super().__init__("Open", section="Tests")
            self._add_output(OutputPort("image", set(IMAGE_TYPES)))
            self._apply_default_params()

        def process_impl(self) -> None: pass

    node = _OpenNode()
    port = next(p for p in node.inputs if p.name == "path")
    assert "mode" not in port.metadata


def test_filepath_param_invalid_mode_raises() -> None:
    with pytest.raises(ValueError, match=r"FilePathParam mode"):
        FilePathParam("x", mode="bogus")


def test_filepath_param_coerce_returns_path() -> None:
    """``_coerce`` produces a :class:`Path`, not a :class:`str`, so
    ``cv2``-side filesystem helpers work without a separate cast."""
    from pathlib import Path
    node = _PathishNode()
    node.target = "foo.png"
    assert isinstance(node.target, Path)


# ── constant=True path ───────────────────────────────────────────────────────

class _ConstantParamNode(NodeBase):
    """Test node mixing port-style and constant-style descriptors."""

    rate = IntParam(2, min=1)  # port-style — auto-creates an InputPort.
    label = StringParam("hello", constant=True)
    enabled = BoolParam(True, constant=True)

    def __init__(self) -> None:
        super().__init__("Const", section="Tests")
        self._add_output(OutputPort("image", set(IMAGE_TYPES)))
        self._apply_default_params()

    def process_impl(self) -> None: pass


def test_constant_descriptor_does_not_create_input_port() -> None:
    node = _ConstantParamNode()
    input_names = {p.name for p in node.inputs}
    assert "rate" in input_names           # port-style descriptor → port
    assert "label" not in input_names      # constant-style → no port
    assert "enabled" not in input_names    # constant-style → no port


def test_constant_descriptor_appears_on_node_params() -> None:
    node = _ConstantParamNode()
    param_names = {p.name for p in node.params}
    assert "label" in param_names
    assert "enabled" in param_names
    assert "rate" not in param_names  # port-style stays out of node.params


def test_constant_descriptor_satisfies_node_param_interface() -> None:
    """The descriptor itself is appended to ``node.params``; the UI's
    existing dispatch reads ``.name``, ``.metadata``,
    ``.default_value`` and ``.upstream`` on each entry, so the
    descriptor must satisfy that contract directly."""
    node = _ConstantParamNode()
    label_desc = next(p for p in node.params if p.name == "label")
    assert label_desc.default_value == "hello"
    assert label_desc.upstream is None
    assert label_desc.metadata["param_type"].name == "STRING"


def test_constant_descriptor_default_applied_at_construction() -> None:
    node = _ConstantParamNode()
    assert node.label == "hello"
    assert node.enabled is True


def test_constant_descriptor_setter_runs_validation() -> None:
    """Constant descriptors share the same coerce/validate/shape pipeline
    as port-style descriptors, so setting through the public attribute
    still goes through the descriptor's __set__."""
    node = _ConstantParamNode()
    node.enabled = 0
    assert node.enabled is False

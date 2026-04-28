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

from core.io_data import IMAGE_TYPES, IoDataType
from core.node_base import NodeBase
from core.params import FloatParam, IntParam, OddIntParam
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


def test_odd_int_param_zero_coerces_to_one_within_min() -> None:
    """0 is even → coerced to 1 → satisfies min=1, no raise. The min
    check intentionally applies to the *coerced* value, so the
    odd-only invariant takes priority over a strict literal min.
    """
    node = _DescriptorNode()
    node.kernel = 0
    assert node.kernel == 1


def test_odd_int_param_negative_below_min_after_coerce_raises() -> None:
    """Negatives still trip min after coerce: -2 → -1 (odd) < min=1."""
    node = _DescriptorNode()
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

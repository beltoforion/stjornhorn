"""Unit tests for NodeBase's port-driven attribute mechanism.

The mechanism auto-populates ``self._<port_name>`` from each connected
input port before :meth:`NodeBase.process_impl` runs, then restores the
pre-call value afterwards so a streamed frame never permanently
overwrites the user-set slider value.
"""
from __future__ import annotations

from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase
from core.port import InputPort, OutputPort


class _AngleNode(NodeBase):
    """Minimal node with a SCALAR ``angle`` input + a backing
    ``self._angle`` attribute, mirroring the param-as-port shape that
    the migration is driving toward."""

    def __init__(self) -> None:
        super().__init__("angle-node", section="Filters")
        self._angle: float = 0.0
        self._fired_with: list[float] = []
        self._add_input(InputPort("angle", {IoDataType.SCALAR}))
        self._add_output(OutputPort("out", {IoDataType.SCALAR}))

    @property
    @override
    def params(self):
        return []

    @property
    def angle(self) -> float:
        return self._angle

    @angle.setter
    def angle(self, value: float) -> None:
        self._angle = float(value)

    @override
    def process_impl(self) -> None:
        # Read the framework-populated attribute exactly the way an
        # ordinary node would today; the test then asserts that this
        # is the streamed value, not the pre-call default.
        self._fired_with.append(self._angle)
        self.outputs[0].send(IoData.from_scalar(self._angle))


def test_streamed_value_is_written_into_backing_attribute() -> None:
    """When a SCALAR upstream sends a value, the framework writes it
    into ``self._angle`` *before* process_impl runs, so the node sees
    the streamed value via plain attribute access."""
    node = _AngleNode()
    node.angle = 0.0  # user-set default
    up = OutputPort("ramp", {IoDataType.SCALAR})
    up.connect(node.inputs[0])

    node.before_run()
    up.send(IoData.from_scalar(45.0))

    assert node._fired_with == [45.0]


def test_post_call_restore_keeps_user_set_default() -> None:
    """After process_impl returns the framework restores the
    pre-call value, so disconnecting the port leaves the user's
    slider value intact rather than pinning the last streamed frame."""
    node = _AngleNode()
    node.angle = 30.0
    up = OutputPort("ramp", {IoDataType.SCALAR})
    up.connect(node.inputs[0])

    node.before_run()
    up.send(IoData.from_scalar(180.0))

    # Inside process_impl angle was 180, but afterwards it's back to 30.
    assert node._fired_with == [180.0]
    assert node.angle == 30.0


def test_multiple_streamed_frames_each_see_their_own_value() -> None:
    """Per-frame independence: every dispatched frame populates the
    attribute fresh, so a 0..N ramp produces N+1 distinct readings."""
    node = _AngleNode()
    node.angle = 0.0
    up = OutputPort("ramp", {IoDataType.SCALAR})
    up.connect(node.inputs[0])

    node.before_run()
    for v in (10.0, 20.0, 30.0):
        up.send(IoData.from_scalar(v))

    assert node._fired_with == [10.0, 20.0, 30.0]
    # Restored to the user-set 0.0 after every frame.
    assert node.angle == 0.0


def test_unconnected_port_does_not_overwrite_attribute() -> None:
    """A port with no upstream data is skipped — the user-set value
    (typically committed by a slider or flow loader) is left alone."""

    class _OptionalAngleNode(NodeBase):
        def __init__(self) -> None:
            super().__init__("opt-angle", section="Filters")
            self._angle: float = 42.0
            self._observed: list[float] = []
            # Required image input so the dispatcher fires (we need
            # *some* trigger), and an optional unconnected angle port.
            self._add_input(InputPort("trigger", {IoDataType.SCALAR}))
            self._add_input(InputPort("angle", {IoDataType.SCALAR}, optional=True))
            self._add_output(OutputPort("out", {IoDataType.SCALAR}))

        @property
        @override
        def params(self):
            return []

        @override
        def process_impl(self) -> None:
            self._observed.append(self._angle)
            self.outputs[0].send(IoData.from_scalar(self._angle))

    node = _OptionalAngleNode()
    up = OutputPort("trig", {IoDataType.SCALAR})
    up.connect(node.inputs[0])

    node.before_run()
    up.send(IoData.from_scalar(0.0))

    # angle port is unconnected — self._angle stays at the user value.
    assert node._observed == [42.0]
    assert node._angle == 42.0


def test_image_input_without_backing_attribute_is_left_alone() -> None:
    """Image-flow ports read via ``self.inputs[i].data``; they have no
    matching ``self._<name>`` attribute on the node. The framework
    must skip them (otherwise it'd try to write an IoData into a
    non-existent slot and pollute the namespace)."""
    import numpy as np

    class _ImageEchoNode(NodeBase):
        def __init__(self) -> None:
            super().__init__("image-echo", section="Filters")
            # Deliberately *no* self._image attribute — confirms the
            # framework's hasattr guard works.
            self._add_input(InputPort("image", {IoDataType.IMAGE}))
            self._add_output(OutputPort("out", {IoDataType.IMAGE}))

        @property
        @override
        def params(self):
            return []

        @override
        def process_impl(self) -> None:
            self.outputs[0].send(self.inputs[0].data)

    node = _ImageEchoNode()
    up = OutputPort("img_up", {IoDataType.IMAGE})
    up.connect(node.inputs[0])

    node.before_run()
    img = np.full((4, 4, 3), 50, dtype=np.uint8)
    up.send(IoData.from_image(img))

    assert not hasattr(node, "_image"), \
        "framework must not auto-create an _image slot on image-flow nodes"


def test_setter_validation_runs_on_streamed_value() -> None:
    """The framework writes via the public attribute name so the
    node's @property.setter still runs — keeping its
    validation/clamping logic in effect for streamed frames just like
    for slider-set values."""

    class _ScaleNode(NodeBase):
        def __init__(self) -> None:
            super().__init__("scale-node", section="Filters")
            self._scale: float = 1.0
            self._fired_with: list[float] = []
            self._add_input(InputPort("scale", {IoDataType.SCALAR}))
            self._add_output(OutputPort("out", {IoDataType.SCALAR}))

        @property
        @override
        def params(self):
            return []

        @property
        def scale(self) -> float:
            return self._scale

        @scale.setter
        def scale(self, value: float) -> None:
            v = float(value)
            if v <= 0.0:
                raise ValueError(f"scale must be > 0 (got {v})")
            self._scale = v

        @override
        def process_impl(self) -> None:
            self._fired_with.append(self._scale)
            self.outputs[0].send(IoData.from_scalar(self._scale))

    node = _ScaleNode()
    node.scale = 2.0  # remembered as the user-set fallback
    up = OutputPort("up", {IoDataType.SCALAR})
    up.connect(node.inputs[0])

    node.before_run()

    # Valid value passes validation and is observed inside process_impl.
    up.send(IoData.from_scalar(0.5))
    assert node._fired_with == [0.5]
    # Restored after the call.
    assert node.scale == 2.0


def test_setter_rejection_rolls_back_partial_writes() -> None:
    """If a setter raises mid-populate (the second port's value is
    invalid), any earlier port's write must be rolled back so the
    node doesn't end up half-mutated."""

    class _TwoSetterNode(NodeBase):
        def __init__(self) -> None:
            super().__init__("two-setter", section="Filters")
            self._a: int = 100
            self._b: float = 1.0
            self._add_input(InputPort("a", {IoDataType.SCALAR}))
            self._add_input(InputPort("b", {IoDataType.SCALAR}))
            self._add_output(OutputPort("out", {IoDataType.SCALAR}))

        @property
        @override
        def params(self):
            return []

        @property
        def a(self) -> int:
            return self._a

        @a.setter
        def a(self, value: int) -> None:
            self._a = int(value)

        @property
        def b(self) -> float:
            return self._b

        @b.setter
        def b(self, value: float) -> None:
            v = float(value)
            if v <= 0.0:
                raise ValueError("b must be > 0")
            self._b = v

        @override
        def process_impl(self) -> None:  # pragma: no cover — won't be reached
            ...

    node = _TwoSetterNode()
    up_a = OutputPort("a_up", {IoDataType.SCALAR})
    up_b = OutputPort("b_up", {IoDataType.SCALAR})
    up_a.connect(node.inputs[0])
    up_b.connect(node.inputs[1])

    node.before_run()
    # a's setter accepts the value; b's setter rejects it. The framework
    # must roll back a so the node's state isn't half-mutated when the
    # exception surfaces upstream.
    up_a.send(IoData.from_scalar(7))
    try:
        up_b.send(IoData.from_scalar(-1.0))
    except ValueError:
        pass  # expected — surfaced by NodeBase.process

    assert node.a == 100, "partial populate must roll back when a later setter raises"
    assert node.b == 1.0

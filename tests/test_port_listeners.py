"""Unit tests for :class:`InputPort`'s multi-listener registration.

Locks down M11: ``set_on_state_changed`` was a single-callback slot
that NodeBase relied on for dispatch; anyone else calling it
silently broke dispatch. The slot is now an
``add_listener`` / ``remove_listener`` pair so multiple observers can
coexist without clobbering each other.
"""
from __future__ import annotations

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase
from core.port import InputPort, OutputPort


def test_listener_fires_on_receive() -> None:
    port = InputPort("in", {IoDataType.SCALAR})
    bucket: list[float] = []
    port.add_listener(lambda: bucket.append(port.data.payload.item()))

    OutputPort("up", {IoDataType.SCALAR}).connect(port)
    port.upstream.send(IoData.from_scalar(7.0))

    assert bucket == [7.0]


def test_listener_fires_on_finish() -> None:
    port = InputPort("in", {IoDataType.SCALAR})
    fired: list[str] = []
    port.add_listener(lambda: fired.append("finish" if port.finished else "data"))

    up = OutputPort("up", {IoDataType.SCALAR})
    up.connect(port)
    up.finish()

    assert fired == ["finish"]


def test_multiple_listeners_fire_in_registration_order() -> None:
    port = InputPort("in", {IoDataType.SCALAR})
    order: list[str] = []
    port.add_listener(lambda: order.append("a"))
    port.add_listener(lambda: order.append("b"))
    port.add_listener(lambda: order.append("c"))

    OutputPort("up", {IoDataType.SCALAR}).connect(port)
    port.upstream.send(IoData.from_scalar(1.0))

    assert order == ["a", "b", "c"]


def test_external_listener_does_not_clobber_dispatcher() -> None:
    """The whole point of M11: NodeBase's dispatcher hookup must
    survive an external observer attaching its own listener — the
    legacy ``set_on_state_changed`` slot was overwritten on every
    call, which silently broke dispatch when anyone else registered
    a callback after the node had already been wired up.
    """

    class _CountingNode(NodeBase):
        def __init__(self) -> None:
            super().__init__("count", section="Filters")
            # Bare port without ``param_type`` metadata so the
            # populate-port-driven-attributes path skips it (we only
            # care that the dispatcher fires once per send here).
            self._add_input(InputPort("x", {IoDataType.SCALAR}))
            self._add_output(OutputPort("out", {IoDataType.SCALAR}))
            self.fired = 0

        def process_impl(self) -> None:
            self.fired += 1
            self.outputs[0].send(IoData.from_scalar(0.0))

    node = _CountingNode()
    spy_fired: list[bool] = []
    # External observer registers AFTER NodeBase wired its dispatcher.
    # Under the old single-slot ``set_on_state_changed`` this would
    # have replaced the dispatcher hookup, leaving ``node.fired == 0``
    # after a send. Multi-listener registration keeps both alive.
    node.inputs[0].add_listener(lambda: spy_fired.append(True))

    up = OutputPort("up", {IoDataType.SCALAR})
    up.connect(node.inputs[0])
    node.before_run()
    up.send(IoData.from_scalar(42.0))

    assert spy_fired == [True]
    assert node.fired == 1


def test_remove_listener_unregisters() -> None:
    port = InputPort("in", {IoDataType.SCALAR})
    fired: list[int] = []

    def listener() -> None:
        fired.append(1)

    port.add_listener(listener)
    up = OutputPort("u", {IoDataType.SCALAR})
    up.connect(port)
    up.send(IoData.from_scalar(1.0))
    assert fired == [1]

    port.remove_listener(listener)
    # Send through the same upstream (still connected) — listener
    # no longer fires now that it's unregistered.
    port.clear()
    up.send(IoData.from_scalar(2.0))
    assert fired == [1]


def test_remove_listener_missing_is_noop() -> None:
    """``remove_listener`` with an unregistered callback is a no-op
    rather than an error — symmetric with idempotent disconnect APIs
    elsewhere."""
    port = InputPort("in", {IoDataType.SCALAR})
    port.remove_listener(lambda: None)  # never raised


def test_listener_can_mutate_listener_list_mid_fire() -> None:
    """A listener that adds / removes listeners mid-fire mustn't
    corrupt the iteration. The implementation iterates a snapshot."""
    port = InputPort("in", {IoDataType.SCALAR})
    fired: list[str] = []

    def adder() -> None:
        fired.append("a")
        port.add_listener(lambda: fired.append("b-late"))

    port.add_listener(adder)
    up = OutputPort("u", {IoDataType.SCALAR})
    up.connect(port)

    up.send(IoData.from_scalar(1.0))
    # First send: adder fires, registers a late listener; the late
    # listener doesn't run on this fire (the implementation iterates
    # a snapshot of the list taken before notification began).
    assert fired == ["a"]

    # Second send: adder fires again *and* the late listener
    # registered during the first send is now in the list and fires.
    port.clear()
    up.send(IoData.from_scalar(2.0))
    assert fired == ["a", "a", "b-late"]

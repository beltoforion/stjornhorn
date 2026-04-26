"""Unit tests for the param-as-port machinery as it stands post-step-6.

Each editable property on a node is declared inline in ``__init__``
as an :class:`InputPort` whose metadata carries a ``"param_type"``
key. :meth:`NodeBase._apply_default_params` reads each such port's
``default_value`` and pushes it onto the matching instance attribute
via the property setter, and :attr:`NodeBase.params` filters the input
list down to those param-style ports for the UI to iterate.
"""
from __future__ import annotations

from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase, NodeParamType, SourceNodeBase
from core.port import InputPort, OutputPort


# ── Per-NodeParamType port type backing ───────────────────────────────────────


def _node_with_port(
    name: str,
    port_type: IoDataType,
    param_type: NodeParamType,
    metadata: dict,
) -> NodeBase:
    """Build a minimal node that declares a single editable input port."""

    class _OnePortNode(NodeBase):
        def __init__(self) -> None:
            super().__init__("one-port", section="Filters")
            setattr(self, f"_{name}", None)
            full_metadata = {**metadata, "param_type": param_type}
            self._add_input(InputPort(
                name,
                {port_type},
                optional=True,
                default_value=metadata.get("default"),
                metadata=full_metadata,
            ))
            self._add_output(OutputPort("out", {IoDataType.SCALAR}))
            self._apply_default_params()

        @override
        def process_impl(self) -> None:  # pragma: no cover
            ...

    return _OnePortNode()


def test_int_param_uses_scalar_port() -> None:
    node = _node_with_port(
        "count", IoDataType.SCALAR, NodeParamType.INT, {"default": 7},
    )
    port = node.inputs[0]
    assert port.name == "count"
    assert port.accepted_types == frozenset({IoDataType.SCALAR})
    assert port.optional is True
    assert port.default_value == 7
    assert port.metadata["param_type"] is NodeParamType.INT


def test_float_param_uses_scalar_port() -> None:
    """INT and FLOAT collapse to SCALAR so any scalar source can drive
    any numeric param without a per-type bridge."""
    node = _node_with_port(
        "ratio", IoDataType.SCALAR, NodeParamType.FLOAT, {"default": 0.5},
    )
    assert node.inputs[0].accepted_types == frozenset({IoDataType.SCALAR})


def test_bool_param_uses_bool_port() -> None:
    node = _node_with_port(
        "enabled", IoDataType.BOOL, NodeParamType.BOOL, {"default": True},
    )
    port = node.inputs[0]
    assert port.accepted_types == frozenset({IoDataType.BOOL})
    assert port.default_value is True


def test_string_param_uses_string_port() -> None:
    node = _node_with_port(
        "title", IoDataType.STRING, NodeParamType.STRING, {"default": "hi"},
    )
    assert node.inputs[0].accepted_types == frozenset({IoDataType.STRING})


def test_enum_param_uses_enum_port() -> None:
    node = _node_with_port(
        "op", IoDataType.ENUM, NodeParamType.ENUM, {"default": 0, "enum": object},
    )
    assert node.inputs[0].accepted_types == frozenset({IoDataType.ENUM})


def test_file_path_param_uses_path_port() -> None:
    node = _node_with_port(
        "file_path",
        IoDataType.PATH,
        NodeParamType.FILE_PATH,
        {"default": "in.png"},
    )
    assert node.inputs[0].accepted_types == frozenset({IoDataType.PATH})


# ── Metadata + default propagation ────────────────────────────────────────────


def test_port_metadata_carries_widget_hints() -> None:
    """Widget hints (min/max/step/etc.) live on the port's metadata
    dict so the inline socket widget can render the right control."""
    node = _node_with_port(
        "angle", IoDataType.SCALAR, NodeParamType.FLOAT,
        {"default": 90.0, "min": 0, "max": 359, "step": 1},
    )
    md = node.inputs[0].metadata
    assert md.get("min") == 0
    assert md.get("max") == 359
    assert md.get("step") == 1


def test_apply_default_params_writes_default_to_attribute() -> None:
    """``_apply_default_params`` reads each editable port's
    ``default_value`` and writes it onto the matching instance
    attribute via the property setter."""

    class _ScaledEcho(NodeBase):
        def __init__(self) -> None:
            super().__init__("scaled-echo", section="Filters")
            self._factor: float = 0.0
            self._add_input(InputPort(
                "factor",
                {IoDataType.SCALAR},
                optional=True,
                default_value=2.5,
                metadata={"default": 2.5, "param_type": NodeParamType.FLOAT},
            ))
            self._add_output(OutputPort("out", {IoDataType.SCALAR}))
            self._apply_default_params()

        @property
        def factor(self) -> float:
            return self._factor

        @factor.setter
        def factor(self, value: float) -> None:
            self._factor = float(value)

        @override
        def process_impl(self) -> None:  # pragma: no cover
            ...

    node = _ScaledEcho()
    assert node.factor == 2.5


# ── params property filters to param-style ports ──────────────────────────────


def test_params_property_returns_only_param_style_ports() -> None:
    """Image-flow inputs (no ``param_type`` in metadata) are filtered
    out so the UI doesn't render a widget for them."""

    class _MixedNode(NodeBase):
        def __init__(self) -> None:
            super().__init__("mixed", section="Filters")
            self._add_input(InputPort("image", {IoDataType.IMAGE}))  # no metadata
            self._add_input(InputPort(
                "size",
                {IoDataType.SCALAR},
                optional=True,
                default_value=3,
                metadata={"default": 3, "param_type": NodeParamType.INT},
            ))
            self._add_output(OutputPort("out", {IoDataType.IMAGE}))
            self._apply_default_params()

        @override
        def process_impl(self) -> None:  # pragma: no cover
            ...

    node = _MixedNode()
    param_ports = node.param_input_ports
    assert len(param_ports) == 1
    assert param_ports[0].name == "size"
    assert param_ports[0].metadata["param_type"] is NodeParamType.INT


def test_params_empty_when_node_has_no_param_style_ports() -> None:
    class _NoParamNode(NodeBase):
        def __init__(self) -> None:
            super().__init__("no-param", section="Filters")
            self._add_input(InputPort("image", {IoDataType.IMAGE}))
            self._add_output(OutputPort("out", {IoDataType.IMAGE}))
            self._apply_default_params()

        @override
        def process_impl(self) -> None:  # pragma: no cover
            ...

    node = _NoParamNode()
    assert node.params == []


# ── End-to-end: drive a port and read the populated attribute ─────────────────


def test_param_port_drive_populates_attribute_via_step2() -> None:
    """Step 2's framework hook still works on top of step-6 declarations:
    a streamed scalar lands on ``self._factor`` before process_impl
    runs and is restored afterwards."""

    class _ScaledEcho(NodeBase):
        def __init__(self) -> None:
            super().__init__("scaled-echo", section="Filters")
            self._factor: float = 1.0
            self._observed: list[float] = []
            self._add_input(InputPort("trigger", {IoDataType.SCALAR}))
            self._add_input(InputPort(
                "factor",
                {IoDataType.SCALAR},
                optional=True,
                default_value=1.0,
                metadata={"default": 1.0, "param_type": NodeParamType.FLOAT},
            ))
            self._add_output(OutputPort("out", {IoDataType.SCALAR}))
            self._apply_default_params()

        @property
        def factor(self) -> float:
            return self._factor

        @factor.setter
        def factor(self, value: float) -> None:
            self._factor = float(value)

        @override
        def process_impl(self) -> None:
            self._observed.append(self._factor)
            trig = self.inputs[0].data.payload.item()
            self.outputs[0].send(IoData.from_scalar(trig * self._factor))

    node = _ScaledEcho()
    factor_port = next(p for p in node.inputs if p.name == "factor")

    up_trig = OutputPort("trig_up", {IoDataType.SCALAR})
    up_factor = OutputPort("fac_up", {IoDataType.SCALAR})
    up_trig.connect(node.inputs[0])
    up_factor.connect(factor_port)

    node.before_run()
    up_trig.send(IoData.from_scalar(10.0))
    up_factor.send(IoData.from_scalar(2.5))

    assert node._observed == [2.5]
    assert node._factor == 1.0  # restored after process_impl


# ── Source nodes get param ports too ──────────────────────────────────────────


def test_source_node_with_params_exposes_param_ports() -> None:
    """SourceNodeBase normally has no inputs. Param-as-port means
    even a source's editable properties get input ports — they're
    just not driven by another node in any normal flow, but the
    abstraction is uniform."""

    class _ParamSource(SourceNodeBase):
        def __init__(self) -> None:
            super().__init__("param-src", section="Sources")
            self._level: int = 0
            self._add_input(InputPort(
                "level",
                {IoDataType.SCALAR},
                optional=True,
                default_value=0,
                metadata={"default": 0, "param_type": NodeParamType.INT},
            ))
            self._add_output(OutputPort("v", {IoDataType.SCALAR}))
            self._apply_default_params()

        @override
        def process_impl(self) -> None:  # pragma: no cover
            ...

    node = _ParamSource()
    assert len(node.param_input_ports) == 1
    assert node.param_input_ports[0].name == "level"
    assert node.param_input_ports[0].accepted_types == frozenset({IoDataType.SCALAR})

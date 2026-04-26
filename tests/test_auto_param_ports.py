"""Unit tests for auto-creation of input ports from NodeParam declarations.

Step 3 of the param-as-port migration: every numeric / boolean /
string / enum / path-typed NodeParam gains an optional
:class:`InputPort` of the matching :class:`IoDataType` so any future
upstream can drive it. Manually-added ports for the same name are
left in place and not duplicated.
"""
from __future__ import annotations

from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import (
    NodeBase,
    NodeParam,
    NodeParamType,
    SourceNodeBase,
)
from core.port import InputPort, OutputPort


# ── Per-NodeParamType auto-port creation ──────────────────────────────────────


def _node_with_param(name: str, param_type: NodeParamType, metadata: dict) -> NodeBase:
    """Build a minimal node that declares a single param of the given
    type — used to verify the auto-port for each NodeParamType."""

    class _OneParamNode(NodeBase):
        def __init__(self) -> None:
            super().__init__("one-param", section="Filters")
            # Set a backing attribute so the @setter (if any) has
            # something to write to. The simplest form: no setter at
            # all — _apply_default_params writes the default via
            # setattr, which falls through to the instance dict.
            setattr(self, f"_{name}", None)
            self._add_output(OutputPort("out", {IoDataType.SCALAR}))
            self._apply_default_params()

        @property
        @override
        def params(self):
            return [NodeParam(name, param_type, metadata)]

        @override
        def process_impl(self) -> None:  # pragma: no cover
            ...

    return _OneParamNode()


def test_int_param_creates_scalar_port() -> None:
    node = _node_with_param("count", NodeParamType.INT, {"default": 7})
    port = node.inputs[0]
    assert port.name == "count"
    assert port.accepted_types == frozenset({IoDataType.SCALAR})
    assert port.optional is True
    assert port.default_value == 7


def test_float_param_creates_scalar_port() -> None:
    """INT and FLOAT collapse to the same SCALAR port type so any
    scalar source can drive any numeric param without a per-type
    bridge."""
    node = _node_with_param("ratio", NodeParamType.FLOAT, {"default": 0.5})
    port = node.inputs[0]
    assert port.accepted_types == frozenset({IoDataType.SCALAR})


def test_bool_param_creates_bool_port() -> None:
    node = _node_with_param("enabled", NodeParamType.BOOL, {"default": True})
    port = node.inputs[0]
    assert port.accepted_types == frozenset({IoDataType.BOOL})
    assert port.default_value is True


def test_string_param_creates_string_port() -> None:
    node = _node_with_param("title", NodeParamType.STRING, {"default": "hi"})
    port = node.inputs[0]
    assert port.accepted_types == frozenset({IoDataType.STRING})


def test_enum_param_creates_enum_port() -> None:
    node = _node_with_param("op", NodeParamType.ENUM, {"default": 0, "enum": object})
    port = node.inputs[0]
    assert port.accepted_types == frozenset({IoDataType.ENUM})


def test_file_path_param_creates_path_port() -> None:
    node = _node_with_param("file_path", NodeParamType.FILE_PATH, {"default": "in.png"})
    port = node.inputs[0]
    assert port.accepted_types == frozenset({IoDataType.PATH})


def test_folder_param_creates_path_port() -> None:
    """FOLDER and FILE_PATH share the PATH port type; the file vs
    folder semantics live in metadata for the widget to interpret."""
    node = _node_with_param("dir", NodeParamType.FOLDER, {"default": "in/"})
    port = node.inputs[0]
    assert port.accepted_types == frozenset({IoDataType.PATH})


# ── Metadata + default propagation ────────────────────────────────────────────


def test_auto_port_copies_metadata_from_param() -> None:
    """Widget hints (min/max/step/etc.) live on the port's metadata
    dict so the inline socket widget can render the right control."""
    meta = {"default": 90.0, "min": 0, "max": 359, "step": 1}
    node = _node_with_param("angle", NodeParamType.FLOAT, meta)
    port = node.inputs[0]
    assert port.metadata.get("min") == 0
    assert port.metadata.get("max") == 359
    assert port.metadata.get("step") == 1


def test_auto_port_default_value_falls_through_to_none_when_param_has_no_default() -> None:
    node = _node_with_param("free", NodeParamType.STRING, {})  # no "default" key
    port = node.inputs[0]
    assert port.default_value is None


# ── Coexistence with manually-declared ports ──────────────────────────────────


class _NodeWithManualPort(NodeBase):
    """Mimics Overlay's pattern: a manual port exists for one param
    *before* _apply_default_params runs. The auto-creator must not
    duplicate it."""

    def __init__(self) -> None:
        super().__init__("manual-and-auto", section="Filters")
        self._scale: float = 1.0
        self._angle: float = 0.0
        # Manual port for ``angle`` only. ``scale`` should be auto-created.
        self._add_input(InputPort("angle", {IoDataType.SCALAR}, optional=True))
        self._add_output(OutputPort("out", {IoDataType.SCALAR}))
        self._apply_default_params()

    @property
    @override
    def params(self):
        return [
            NodeParam("scale", NodeParamType.FLOAT, {"default": 1.0}),
            NodeParam("angle", NodeParamType.FLOAT, {"default": 0.0}),
        ]

    @override
    def process_impl(self) -> None:  # pragma: no cover
        ...


def test_manual_port_is_not_duplicated() -> None:
    node = _NodeWithManualPort()
    angle_ports = [p for p in node.inputs if p.name == "angle"]
    assert len(angle_ports) == 1


def test_manual_port_keeps_its_index() -> None:
    """Existing flow files reference connections by port index. The
    manual ``angle`` port stays at the index the subclass placed it
    so saved flows still load identically."""
    node = _NodeWithManualPort()
    assert node.inputs[0].name == "angle"


def test_missing_port_for_other_params_is_auto_created() -> None:
    node = _NodeWithManualPort()
    names = [p.name for p in node.inputs]
    assert "scale" in names
    assert names.count("scale") == 1


# ── No-param nodes get no auto-ports ──────────────────────────────────────────


def test_node_with_no_params_gets_no_extra_ports() -> None:
    """Display has zero NodeParams; the auto-port logic must not add
    spurious ports to it."""

    class _NoParamNode(NodeBase):
        def __init__(self) -> None:
            super().__init__("no-param", section="Filters")
            self._add_input(InputPort("image", {IoDataType.IMAGE}))
            self._add_output(OutputPort("out", {IoDataType.IMAGE}))
            self._apply_default_params()

        @property
        @override
        def params(self):
            return []

        @override
        def process_impl(self) -> None:  # pragma: no cover
            ...

    node = _NoParamNode()
    assert len(node.inputs) == 1
    assert node.inputs[0].name == "image"


# ── End-to-end: auto-port can be driven ───────────────────────────────────────


def test_auto_port_can_be_driven_via_step2_populate() -> None:
    """The whole point of step 3: a freshly-introduced numeric param
    becomes drivable without any Overlay-style manual code in the
    node. Step 2's framework hook reads from the auto-created port and
    writes self._<name> before process_impl runs."""

    class _ScaledEcho(NodeBase):
        def __init__(self) -> None:
            super().__init__("scaled-echo", section="Filters")
            self._factor: float = 1.0
            self._observed: list[float] = []
            self._add_input(InputPort("trigger", {IoDataType.SCALAR}))
            self._add_output(OutputPort("out", {IoDataType.SCALAR}))
            self._apply_default_params()

        @property
        @override
        def params(self):
            return [NodeParam("factor", NodeParamType.FLOAT, {"default": 1.0})]

        @property
        def factor(self) -> float:
            return self._factor

        @factor.setter
        def factor(self, value: float) -> None:
            self._factor = float(value)

        @override
        def process_impl(self) -> None:
            # Reads self._factor as a plain attribute — framework
            # populates it from the auto-created ``factor`` port.
            self._observed.append(self._factor)
            trig = self.inputs[0].data.payload.item()
            self.outputs[0].send(IoData.from_scalar(trig * self._factor))

    node = _ScaledEcho()
    # auto-port for ``factor`` should now exist
    factor_ports = [p for p in node.inputs if p.name == "factor"]
    assert len(factor_ports) == 1
    factor_port = factor_ports[0]
    assert factor_port.accepted_types == frozenset({IoDataType.SCALAR})

    # Drive both the trigger and the factor from upstreams.
    up_trig = OutputPort("trig_up", {IoDataType.SCALAR})
    up_factor = OutputPort("fac_up", {IoDataType.SCALAR})
    up_trig.connect(node.inputs[0])
    up_factor.connect(factor_port)

    node.before_run()
    up_trig.send(IoData.from_scalar(10.0))
    up_factor.send(IoData.from_scalar(2.5))

    assert node._observed == [2.5]
    # factor restored to user-set 1.0 after process_impl returns
    assert node._factor == 1.0


# ── Source nodes get auto-ports too ───────────────────────────────────────────


def test_source_node_with_params_gets_auto_ports() -> None:
    """SourceNodeBase normally has no inputs. Param-as-port means
    even a source's editable properties get input ports — they're
    just not driven by another node in any normal flow, but the
    abstraction is uniform."""

    class _ParamSource(SourceNodeBase):
        def __init__(self) -> None:
            super().__init__("param-src", section="Sources")
            self._level: int = 0
            self._add_output(OutputPort("v", {IoDataType.SCALAR}))
            self._apply_default_params()

        @property
        @override
        def params(self):
            return [NodeParam("level", NodeParamType.INT, {"default": 0})]

        @override
        def process_impl(self) -> None:  # pragma: no cover
            ...

    node = _ParamSource()
    assert len(node.inputs) == 1
    assert node.inputs[0].name == "level"
    assert node.inputs[0].accepted_types == frozenset({IoDataType.SCALAR})

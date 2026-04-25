from __future__ import annotations

from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import SourceNodeBase, NodeParam, NodeParamType
from core.port import OutputPort


class ConstantValue(SourceNodeBase):
    """Reactive source that emits a single SCALAR value, latched downstream.

    Mirror of :class:`~nodes.sources.image_source.ImageSource` for
    numeric pipelines: the value is emitted exactly once per run, and
    stays latched on whichever streaming consumer it feeds (see
    :meth:`core.port.InputPort.clear` for the latching mechanism).
    Useful as the fixed input to a :class:`~nodes.filters.math.Math`
    node — e.g. multiplying every value of a streaming
    :class:`~nodes.sources.value_source.ValueSource` by a constant.

    Reactive: editing ``value`` re-runs the flow automatically so the
    update is visible immediately, the same way ImageSource refreshes
    when the file path changes.
    """

    def __init__(self) -> None:
        super().__init__("Constant Value", section="Sources")
        self._value: float = 0.0
        self._add_output(OutputPort("value", {IoDataType.SCALAR}))
        self._apply_default_params()

    # ── Parameters ─────────────────────────────────────────────────────────────

    @property
    @override
    def params(self) -> list[NodeParam]:
        return [
            NodeParam("value", NodeParamType.FLOAT, {"default": 0.0}),
        ]

    @property
    def value(self) -> float:
        return self._value

    @value.setter
    def value(self, v: float) -> None:
        self._value = float(v)

    # ── SourceNodeBase interface ────────────────────────────────────────────────

    @property
    @override
    def is_reactive(self) -> bool:
        return True

    @override
    def process_impl(self) -> None:
        self.outputs[0].send(IoData.from_scalar(self._value))

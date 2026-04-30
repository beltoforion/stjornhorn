from __future__ import annotations

from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import SourceNodeBase
from core.params import FloatParam
from core.port import OutputPort


class ConstantValue(SourceNodeBase):
    """Reactive source that emits a single SCALAR value, latched downstream.

    The value is emitted once per run and stays latched on streaming
    consumers — useful as the fixed input to a :class:`Math` node.
    Reactive: editing ``value`` re-runs the flow automatically.
    """

    value = FloatParam(0.0, constant=True)

    def __init__(self) -> None:
        super().__init__("Constant Value", section="Sources")
        self._add_output(OutputPort("value", {IoDataType.SCALAR}))
        self._apply_default_params()

    @property
    @override
    def is_reactive(self) -> bool:
        return True

    @override
    def process_impl(self) -> None:
        self.outputs[0].send(IoData.from_scalar(self._value))

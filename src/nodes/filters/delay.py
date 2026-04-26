from __future__ import annotations

import time

from typing_extensions import override

from core.io_data import IMAGE_TYPES, IoDataType
from core.node_base import NodeBase, NodeParamType
from core.port import InputPort, OutputPort


class Delay(NodeBase):
    """Debug node that sleeps for ``delay_seconds`` before forwarding its input.

    Exists to make pipeline timing visible during development — dropping it
    between two nodes introduces a deterministic pause so scheduling, status
    bar updates and progress indicators can be observed without contrived
    workloads. The image payload is passed straight through unchanged.
    """

    def __init__(self) -> None:
        super().__init__("Delay", section="Debug")
        self._delay_seconds: float = 5.0

        self._add_input(InputPort("image", set(IMAGE_TYPES)))
        self._add_input(InputPort(
            "delay_seconds",
            {IoDataType.SCALAR},
            optional=True,
            default_value=5.0,
            metadata={"default": 5.0, "param_type": NodeParamType.FLOAT},
        ))
        self._add_output(OutputPort("image", set(IMAGE_TYPES)))

        self._apply_default_params()

    @property
    def delay_seconds(self) -> float:
        return self._delay_seconds

    @delay_seconds.setter
    def delay_seconds(self, value: float) -> None:
        v = float(value)
        if v < 0:
            raise ValueError(f"delay_seconds must be >= 0 (got {v})")
        self._delay_seconds = v

    @override
    def process_impl(self) -> None:
        in_data = self.inputs[0].data
        time.sleep(self._delay_seconds)
        self.outputs[0].send(in_data)

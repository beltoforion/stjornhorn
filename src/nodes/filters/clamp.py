from __future__ import annotations

import numpy as np
from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase
from core.params import FloatParam
from core.port import InputPort, OutputPort


class Clamp(NodeBase):
    """Clamp a SCALAR stream to ``[min_value, max_value]``.

    If ``min_value > max_value`` the bounds are swapped before
    clamping, so a transiently-inverted range during editing is
    tolerated.
    """

    min_value = FloatParam(
        0.0,
        description="Lower bound. Values below this are clipped up to it.",
    )
    max_value = FloatParam(
        1.0,
        description=(
            "Upper bound. Values above this are clipped down to it. "
            "If the upper bound ends up below the lower bound the "
            "two are swapped so the range is always usable."
        ),
    )

    HEADER_ICON = "vertical_align_center"

    def __init__(self) -> None:
        super().__init__("Clamp", section="Math")
        self._add_input(InputPort("value", {IoDataType.SCALAR}))
        self._add_output(OutputPort("value", {IoDataType.SCALAR}))
        self._apply_default_params()

    @override
    def process_impl(self) -> None:
        v: np.ndarray = self.inputs[0].data.payload
        lo, hi = self._min_value, self._max_value
        if lo > hi:
            lo, hi = hi, lo
        clamped = np.clip(v, lo, hi)
        self.outputs[0].send(IoData.from_scalar(clamped))

from __future__ import annotations

from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import SourceNodeBase, NodeParam, NodeParamType
from core.port import OutputPort


class ValueSource(SourceNodeBase):
    """Source node that emits a SCALAR counter, one value per frame.

    Drives downstream nodes with a numeric stream — useful as a test
    probe for the new SCALAR payload type and, once param-driven ports
    land, as a way to animate any numeric parameter (e.g. an Overlay
    rotation angle that ramps from 0 to 360).

    Parameters:
      min_value  -- first emitted integer (inclusive)
      max_value  -- last emitted integer (inclusive)
      multiplier -- each emitted value is ``n * multiplier``; the result
                    is float when ``multiplier`` is non-integer, int when
                    it's exactly ``1.0`` and the count is an int
      loop       -- when False (default), emits ``min..max`` once and
                    finishes; when True, repeats the range
                    :data:`_LOOP_CYCLES` times so the wraparound is
                    observable in a finite run

    The looping cycle count is bounded because the flow runner has no
    cancel mechanism — an unbounded ``loop=True`` would hang every Run.
    """

    #: How many times the counter cycles when ``loop=True``. Bounded so
    #: a Run terminates without a Stop button (which the flow runner
    #: doesn't have yet).
    _LOOP_CYCLES: int = 10

    def __init__(self) -> None:
        super().__init__("Value Source", section="Sources")
        self._min_value: int = 0
        self._max_value: int = 99
        self._multiplier: float = 1.0
        self._loop: bool = False
        self._add_output(OutputPort("value", {IoDataType.SCALAR}))
        self._apply_default_params()

    # ── Parameters ─────────────────────────────────────────────────────────────

    @property
    @override
    def params(self) -> list[NodeParam]:
        return [
            NodeParam("min_value",  NodeParamType.INT,   {"default": 0}),
            NodeParam("max_value",  NodeParamType.INT,   {"default": 99}),
            NodeParam("multiplier", NodeParamType.FLOAT, {"default": 1.0}),
            NodeParam("loop",       NodeParamType.BOOL,  {"default": False}),
        ]

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def min_value(self) -> int:
        return self._min_value

    @min_value.setter
    def min_value(self, value: int) -> None:
        self._min_value = int(value)

    @property
    def max_value(self) -> int:
        return self._max_value

    @max_value.setter
    def max_value(self, value: int) -> None:
        self._max_value = int(value)

    @property
    def multiplier(self) -> float:
        return self._multiplier

    @multiplier.setter
    def multiplier(self, value: float) -> None:
        self._multiplier = float(value)

    @property
    def loop(self) -> bool:
        return self._loop

    @loop.setter
    def loop(self, value: bool) -> None:
        self._loop = bool(value)

    # ── SourceNodeBase interface ────────────────────────────────────────────────

    @override
    def process_impl(self) -> None:
        # Empty range — nothing to emit. Don't raise; the flow can still
        # be valid (a downstream filter might tolerate zero frames), so
        # log nothing and return.
        if self._max_value < self._min_value:
            return

        cycles = self._LOOP_CYCLES if self._loop else 1
        # Keep integer output when multiplier is exactly 1.0, so a
        # downstream Display shows "42" instead of "42.0". Any other
        # multiplier promotes the value to float.
        is_unit_mult = self._multiplier == 1.0
        for _ in range(cycles):
            for n in range(self._min_value, self._max_value + 1):
                value: int | float = n if is_unit_mult else n * self._multiplier
                self.outputs[0].send(IoData.from_scalar(value))

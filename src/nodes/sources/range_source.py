from __future__ import annotations

import math
from collections.abc import Iterator

from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import SourceNodeBase
from core.params import FloatParam, IntParam
from core.port import OutputPort


class RangeSource(SourceNodeBase):
    """Source node that emits a SCALAR range, one value per frame.

    Drives downstream nodes with a numeric stream — animate a
    Math expression's ``a``, an Overlay's rotation angle, etc.
    Whole-number increments emit ints; fractional increments emit
    floats.
    """

    min_value = IntParam(0, constant=True)
    max_value = IntParam(99, constant=True)
    increment = FloatParam(1.0, min=0.0, min_exclusive=True, constant=True)

    HEADER_ICON = "linear_scale"

    def __init__(self) -> None:
        super().__init__("Range Source", section="Sources")
        self._add_output(OutputPort("value", {IoDataType.SCALAR}))
        self._apply_default_params()

    @override
    def iter_frames(self) -> Iterator[None]:
        """Per-frame generator: one ``yield`` per emitted scalar.

        Letting :class:`core.flow.Flow.run` round-robin streaming
        sources requires this — without per-frame yielding two
        ``RangeSource``s feeding two param ports on the same node
        produce only one composite frame total (the first source
        drains entirely before the second sends anything; see
        :meth:`SourceNodeBase.iter_frames`).
        """
        # Defensive — both can only happen if a setter was bypassed
        # (the increment setter rejects 0 / negatives, and an empty
        # range just emits nothing rather than raising).
        if self._increment <= 0.0:
            return
        if self._max_value < self._min_value:
            return

        # Whole-number increment + integer bounds → emit ints, so a
        # downstream Display shows ``42`` rather than ``42.0``. Any
        # fractional increment promotes every emitted value to float.
        emit_int = self._increment.is_integer()
        # Tolerance on the upper bound so float drift (e.g. 10 *
        # 0.1 == 1.0000000000000002) doesn't truncate the last value.
        tol = abs(self._increment) * 1e-9
        n = 0
        while True:
            value: int | float = self._min_value + n * self._increment
            if value > self._max_value + tol:
                break
            if emit_int:
                value = int(value)
            self.outputs[0].send(IoData.from_scalar(value))
            n += 1
            yield

    @override
    def tick_count(self) -> int | None:
        if self._increment <= 0.0 or self._max_value < self._min_value:
            return 0
        return math.floor((self._max_value - self._min_value) / self._increment) + 1

    @override
    def process_impl(self) -> None:
        """Direct-invocation path used by tests: drain :meth:`iter_frames`
        in one call, mirroring the pre-round-robin all-at-once semantics."""
        for _ in self.iter_frames():
            pass

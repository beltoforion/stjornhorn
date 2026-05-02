from __future__ import annotations

import pandas as pd
from typing_extensions import override

from core.io_data import IoData, IoDataType, IoMeta
from core.node_base import NodeBase
from core.params import IntParam
from core.port import InputPort, OutputPort


class SlidingWindow(NodeBase):
    """Slice a DATASET into a sliding window driven by a SCALAR clock.

    Each tick on ``window_index`` re-emits two DATASETs — both stamped
    with ``window_start`` / ``window_end`` (sample-row indices) in
    :class:`~core.io_data.IoMeta`:

    * ``dataset_windowed`` — the slice
      ``df.iloc[start + idx*step : start + idx*step + window_size]``;
      what an :class:`Hodogram` or any windowed analytic plugs into.
    * ``dataset_full`` — the unmodified input dataset, re-stamped per
      tick with the current window bounds; lets a downstream plotter
      (typically :class:`PlotSeries`) draw the full trace and overlay a
      moving band without needing a dedicated wire for each band
      endpoint. Carries the same DataFrame reference across ticks so
      identity-based caches downstream stay warm.

    The ``dataset`` input is held (``hold_last=True``) so a one-shot
    upstream (CsvSource → SlidingWindow) survives across the streaming
    clock's many ticks. When the index walks past the end of the
    dataset, ``process_impl`` emits nothing — the lifecycle ends
    naturally as soon as the upstream counter finishes.
    """

    window_size = IntParam(
        100,
        min=1,
        constant=True,
        unit="samples",
        description=(
            "Number of rows in each emitted slice. The window keeps "
            "this size until it bumps the end of the dataset, where it "
            "is clamped (last frame may be shorter)."
        ),
    )
    step = IntParam(
        1,
        min=1,
        constant=True,
        unit="samples",
        description=(
            "Samples the window advances per tick. Use 1 for a one-sample "
            "scan; use ``window_size`` for non-overlapping windows."
        ),
    )
    start = IntParam(
        0,
        min=0,
        constant=True,
        unit="samples",
        description="First sample (row index) included in the very first window.",
    )

    HEADER_ICON = "timeline"

    def __init__(self) -> None:
        super().__init__("Sliding Window", section="Data")
        # ``dataset`` is held so a one-shot CsvSource can drive a long
        # streaming clock. The clock (``window_index``) is the lifecycle
        # driver — every tick fires the node, every finish ends it.
        self._add_input(InputPort("dataset", {IoDataType.DATASET}, hold_last=True))
        self._add_input(InputPort("window_index", {IoDataType.SCALAR}))
        self._add_output(OutputPort("dataset_windowed", {IoDataType.DATASET}))
        self._add_output(OutputPort("dataset_full",     {IoDataType.DATASET}))
        self._apply_default_params()

    @override
    def process_impl(self) -> None:
        df: pd.DataFrame = self.inputs[0].data.payload
        idx = int(self.inputs[1].data.payload)
        s = self._start + idx * self._step
        # Past the end → no emission; the run ends when the upstream
        # counter finishes and propagates lifecycle through the graph.
        if s >= len(df):
            return
        # Clamp so the last partial window still produces a valid slice
        # rather than an empty DataFrame the renderer can't plot.
        e = min(s + self._window_size, len(df))

        slice_df = df.iloc[s:e].copy()
        # ``DataFrame.copy`` preserves ``attrs`` in modern pandas, but
        # be explicit — losing ``units`` / ``sample_rate`` here would
        # silently strip the metadata channel that DATASET exists for.
        slice_df.attrs = dict(df.attrs)
        meta = IoMeta(window_start=s, window_end=e)
        self.outputs[0].send(IoData.from_dataset(slice_df, meta=meta))
        # Passthrough emits the *same* DataFrame reference each tick so
        # downstream identity-based caches (PlotSeries trace cache) stay
        # warm — the ``copy()`` above is for the slice only, leaving
        # the source DataFrame untouched.
        self.outputs[1].send(IoData.from_dataset(df, meta=meta))

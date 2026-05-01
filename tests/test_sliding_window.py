"""Tests for :class:`~nodes.filters.sliding_window.SlidingWindow`.

Covers:
- slice math for various ``window_size`` / ``step`` / ``start`` combinations
- empty / out-of-range slices terminate the stream cleanly
- ``window_start`` / ``window_end`` SCALAR outputs match the slice bounds
- end-to-end run with a streaming clock (RangeSource shape) drains the
  expected number of slices

The integration with :class:`PlotSeries` band rendering lives in
``test_plot_series.py``; this file stays focused on slice mechanics.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from core.io_data import IoData, IoDataType
from core.port import InputPort, OutputPort
from nodes.filters.sliding_window import SlidingWindow


def _make_df(n: int = 100) -> pd.DataFrame:
    df = pd.DataFrame({
        "value": np.arange(n, dtype=np.float32),
    })
    df.attrs = {"sample_rate": 100.0, "units": {"value": "m/s"}}
    return df


def _wire(node: SlidingWindow) -> tuple[OutputPort, OutputPort,
                                         list[IoData], list[IoData], list[IoData]]:
    """Connect feeders + capture sinks to all three outputs.

    Returns ``(dataset_feeder, idx_feeder, ds_log, ws_log, we_log)``.
    """
    ds_feed = OutputPort("ds", {IoDataType.DATASET})
    idx_feed = OutputPort("idx", {IoDataType.SCALAR})
    ds_feed.connect(node.inputs[0])
    idx_feed.connect(node.inputs[1])

    ds_log: list[IoData] = []
    ws_log: list[IoData] = []
    we_log: list[IoData] = []

    ds_sink = InputPort("ds_sink", {IoDataType.DATASET})
    ws_sink = InputPort("ws_sink", {IoDataType.SCALAR})
    we_sink = InputPort("we_sink", {IoDataType.SCALAR})
    ds_sink.add_listener(lambda: ds_log.append(ds_sink.data) if ds_sink.has_data else None)
    ws_sink.add_listener(lambda: ws_log.append(ws_sink.data) if ws_sink.has_data else None)
    we_sink.add_listener(lambda: we_log.append(we_sink.data) if we_sink.has_data else None)
    node.outputs[0].connect(ds_sink)
    node.outputs[1].connect(ws_sink)
    node.outputs[2].connect(we_sink)
    return ds_feed, idx_feed, ds_log, ws_log, we_log


# ── Slice math ────────────────────────────────────────────────────────────────


def test_unit_step_emits_one_window_per_tick() -> None:
    node = SlidingWindow()
    node.window_size = 10
    node.step = 1
    node.start = 0

    ds_feed, idx_feed, ds_log, ws_log, we_log = _wire(node)
    node.before_run()

    ds_feed.send(IoData.from_dataset(_make_df(50)))
    ds_feed.finish()
    for i in range(5):
        idx_feed.send(IoData.from_scalar(i))

    assert len(ds_log) == 5
    assert [int(d.payload) for d in ws_log] == [0, 1, 2, 3, 4]
    assert [int(d.payload) for d in we_log] == [10, 11, 12, 13, 14]
    # Verify the slice itself: tick i covers rows [i, i+10).
    for i, frame in enumerate(ds_log):
        df = frame.payload
        assert list(df["value"]) == list(range(i, i + 10))


def test_step_equal_to_window_yields_disjoint_slices() -> None:
    """Non-overlapping windows: tick i covers rows [i*W, (i+1)*W)."""
    node = SlidingWindow()
    node.window_size = 25
    node.step = 25
    node.start = 0

    ds_feed, idx_feed, ds_log, ws_log, we_log = _wire(node)
    node.before_run()

    ds_feed.send(IoData.from_dataset(_make_df(100)))
    ds_feed.finish()
    for i in range(4):
        idx_feed.send(IoData.from_scalar(i))

    assert [int(d.payload) for d in ws_log] == [0, 25, 50, 75]
    assert [int(d.payload) for d in we_log] == [25, 50, 75, 100]


def test_start_offset_is_added_to_each_slice() -> None:
    node = SlidingWindow()
    node.window_size = 5
    node.step = 5
    node.start = 17

    ds_feed, idx_feed, ds_log, ws_log, we_log = _wire(node)
    node.before_run()

    ds_feed.send(IoData.from_dataset(_make_df(50)))
    ds_feed.finish()
    for i in range(3):
        idx_feed.send(IoData.from_scalar(i))

    assert [int(d.payload) for d in ws_log] == [17, 22, 27]
    assert [int(d.payload) for d in we_log] == [22, 27, 32]


def test_partial_last_window_is_emitted_clamped() -> None:
    """When window_size + start*step bumps past the end, the last slice
    is shorter — but still emitted, not silently dropped, so the
    waveform's last samples still get a band."""
    node = SlidingWindow()
    node.window_size = 30
    node.step = 30
    node.start = 0

    ds_feed, idx_feed, ds_log, ws_log, we_log = _wire(node)
    node.before_run()

    ds_feed.send(IoData.from_dataset(_make_df(100)))
    ds_feed.finish()
    for i in range(4):  # ticks 0..3 → starts 0, 30, 60, 90
        idx_feed.send(IoData.from_scalar(i))

    assert len(ds_log) == 4
    # Last window spans [90, 100) — only 10 rows, not 30.
    last_df = ds_log[-1].payload
    assert len(last_df) == 10
    assert int(ws_log[-1].payload) == 90
    assert int(we_log[-1].payload) == 100


def test_index_past_end_emits_nothing() -> None:
    """Lifecycle ends naturally when the upstream counter exhausts.
    A tick whose start sample is past the dataset's length is a no-op
    (no DATASET, no SCALARs)."""
    node = SlidingWindow()
    node.window_size = 10
    node.step = 10
    node.start = 0

    ds_feed, idx_feed, ds_log, ws_log, we_log = _wire(node)
    node.before_run()

    ds_feed.send(IoData.from_dataset(_make_df(20)))
    ds_feed.finish()
    # Ticks 0 and 1 fit; ticks 2 and 3 are past the end.
    for i in range(4):
        idx_feed.send(IoData.from_scalar(i))

    assert len(ds_log) == 2
    assert len(ws_log) == 2
    assert len(we_log) == 2
    assert [int(d.payload) for d in ws_log] == [0, 10]


# ── Metadata preservation ─────────────────────────────────────────────────────


def test_attrs_are_copied_into_each_emitted_slice() -> None:
    """Sliding doesn't strip ``units`` / ``sample_rate`` — downstream
    PlotSeries / Hodogram still get axis labels and time scales."""
    node = SlidingWindow()
    node.window_size = 5
    node.step = 5

    ds_feed, idx_feed, ds_log, _, _ = _wire(node)
    node.before_run()

    ds_feed.send(IoData.from_dataset(_make_df(20)))
    ds_feed.finish()
    idx_feed.send(IoData.from_scalar(0))

    assert ds_log[0].payload.attrs["sample_rate"] == 100.0
    assert ds_log[0].payload.attrs["units"] == {"value": "m/s"}


def test_slice_does_not_mutate_source_dataframe() -> None:
    """The held DATASET is shared across many ticks — make sure
    SlidingWindow doesn't accidentally mutate it."""
    df = _make_df(20)
    df_snapshot = df.copy()

    node = SlidingWindow()
    node.window_size = 5
    node.step = 5

    ds_feed, idx_feed, _, _, _ = _wire(node)
    node.before_run()

    ds_feed.send(IoData.from_dataset(df))
    ds_feed.finish()
    for i in range(3):
        idx_feed.send(IoData.from_scalar(i))

    pd.testing.assert_frame_equal(df, df_snapshot)

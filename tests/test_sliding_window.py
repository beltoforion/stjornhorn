"""Tests for :class:`~nodes.filters.sliding_window.SlidingWindow`.

Covers:
- slice math for various ``window_size`` / ``step`` / ``start`` combinations
- empty / out-of-range slices terminate the stream cleanly
- ``window_start`` / ``window_end`` arrive in :class:`IoMeta` on both the
  slice and the passthrough output
- the passthrough output preserves DataFrame identity across ticks so a
  downstream identity-based cache (``PlotSeries``) stays warm

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


def _wire(node: SlidingWindow) -> tuple[
    OutputPort, OutputPort, list[IoData], list[IoData],
]:
    """Connect feeders + capture sinks to both DATASET outputs.

    Returns ``(dataset_feeder, idx_feeder, slice_log, full_log)``.
    """
    ds_feed = OutputPort("ds", {IoDataType.DATASET})
    idx_feed = OutputPort("idx", {IoDataType.SCALAR})
    ds_feed.connect(node.inputs[0])
    idx_feed.connect(node.inputs[1])

    slice_log: list[IoData] = []
    full_log:  list[IoData] = []

    slice_sink = InputPort("slice_sink", {IoDataType.DATASET})
    full_sink  = InputPort("full_sink",  {IoDataType.DATASET})
    slice_sink.add_listener(
        lambda: slice_log.append(slice_sink.data) if slice_sink.has_data else None,
    )
    full_sink.add_listener(
        lambda: full_log.append(full_sink.data) if full_sink.has_data else None,
    )
    node.outputs[0].connect(slice_sink)
    node.outputs[1].connect(full_sink)
    return ds_feed, idx_feed, slice_log, full_log


# ── Slice math ────────────────────────────────────────────────────────────────


def test_unit_step_emits_one_window_per_tick() -> None:
    node = SlidingWindow()
    node.window_size = 10
    node.step = 1
    node.start = 0

    ds_feed, idx_feed, slice_log, _ = _wire(node)
    node.before_run()

    ds_feed.send(IoData.from_dataset(_make_df(50)))
    ds_feed.finish()
    for i in range(5):
        idx_feed.send(IoData.from_scalar(i))

    assert len(slice_log) == 5
    for i, frame in enumerate(slice_log):
        df = frame.payload
        assert list(df["value"]) == list(range(i, i + 10))


def test_step_equal_to_window_yields_disjoint_slices() -> None:
    """Non-overlapping windows: tick i covers rows [i*W, (i+1)*W)."""
    node = SlidingWindow()
    node.window_size = 25
    node.step = 25
    node.start = 0

    ds_feed, idx_feed, slice_log, _ = _wire(node)
    node.before_run()

    ds_feed.send(IoData.from_dataset(_make_df(100)))
    ds_feed.finish()
    for i in range(4):
        idx_feed.send(IoData.from_scalar(i))

    starts = [int(d.meta["window_start"]) for d in slice_log]
    ends   = [int(d.meta["window_end"])   for d in slice_log]
    assert starts == [0, 25, 50, 75]
    assert ends   == [25, 50, 75, 100]


def test_start_offset_is_added_to_each_slice() -> None:
    node = SlidingWindow()
    node.window_size = 5
    node.step = 5
    node.start = 17

    ds_feed, idx_feed, slice_log, _ = _wire(node)
    node.before_run()

    ds_feed.send(IoData.from_dataset(_make_df(50)))
    ds_feed.finish()
    for i in range(3):
        idx_feed.send(IoData.from_scalar(i))

    starts = [int(d.meta["window_start"]) for d in slice_log]
    ends   = [int(d.meta["window_end"])   for d in slice_log]
    assert starts == [17, 22, 27]
    assert ends   == [22, 27, 32]


def test_partial_last_window_is_emitted_clamped() -> None:
    """When window_size + start*step bumps past the end, the last slice
    is shorter — but still emitted, not silently dropped, so the
    waveform's last samples still get a band."""
    node = SlidingWindow()
    node.window_size = 30
    node.step = 30
    node.start = 0

    ds_feed, idx_feed, slice_log, _ = _wire(node)
    node.before_run()

    ds_feed.send(IoData.from_dataset(_make_df(100)))
    ds_feed.finish()
    for i in range(4):  # ticks 0..3 → starts 0, 30, 60, 90
        idx_feed.send(IoData.from_scalar(i))

    assert len(slice_log) == 4
    # Last window spans [90, 100) — only 10 rows, not 30.
    last = slice_log[-1]
    assert len(last.payload) == 10
    assert int(last.meta["window_start"]) == 90
    assert int(last.meta["window_end"])   == 100


def test_index_past_end_emits_nothing() -> None:
    """Lifecycle ends naturally when the upstream counter exhausts.
    A tick whose start sample is past the dataset's length is a no-op
    on both outputs."""
    node = SlidingWindow()
    node.window_size = 10
    node.step = 10
    node.start = 0

    ds_feed, idx_feed, slice_log, full_log = _wire(node)
    node.before_run()

    ds_feed.send(IoData.from_dataset(_make_df(20)))
    ds_feed.finish()
    # Ticks 0 and 1 fit; ticks 2 and 3 are past the end.
    for i in range(4):
        idx_feed.send(IoData.from_scalar(i))

    assert len(slice_log) == 2
    assert len(full_log)  == 2
    assert [int(d.meta["window_start"]) for d in slice_log] == [0, 10]


# ── Passthrough output ────────────────────────────────────────────────────────


def test_passthrough_emits_full_dataset_each_tick() -> None:
    """``dataset_full`` carries the unmodified input on every tick so a
    downstream PlotSeries can render the full waveform with a moving
    band."""
    node = SlidingWindow()
    node.window_size = 10
    node.step = 10

    ds_feed, idx_feed, _, full_log = _wire(node)
    node.before_run()

    df = _make_df(50)
    ds_feed.send(IoData.from_dataset(df))
    ds_feed.finish()
    for i in range(3):
        idx_feed.send(IoData.from_scalar(i))

    assert len(full_log) == 3
    for f in full_log:
        # Every emit carries the full DataFrame, not the slice.
        assert len(f.payload) == 50


def test_passthrough_preserves_dataframe_identity_across_ticks() -> None:
    """The passthrough wraps the *same* DataFrame reference each tick so
    PlotSeries' identity-based trace cache stays warm across the
    streaming clock — re-rendering matplotlib once per dataset, not
    once per tick."""
    node = SlidingWindow()
    node.window_size = 10
    node.step = 10

    ds_feed, idx_feed, _, full_log = _wire(node)
    node.before_run()

    df = _make_df(50)
    ds_feed.send(IoData.from_dataset(df))
    ds_feed.finish()
    for i in range(4):
        idx_feed.send(IoData.from_scalar(i))

    payload_ids = {id(f.payload) for f in full_log}
    assert len(payload_ids) == 1, (
        f"expected one shared DataFrame across ticks, got {len(payload_ids)}"
    )


def test_passthrough_meta_carries_window_bounds() -> None:
    """Both outputs carry ``window_start`` / ``window_end`` in their
    meta — the slice for downstream window-aware analytics, the
    passthrough for the full-trace plotter."""
    node = SlidingWindow()
    node.window_size = 8
    node.step = 4

    ds_feed, idx_feed, slice_log, full_log = _wire(node)
    node.before_run()

    ds_feed.send(IoData.from_dataset(_make_df(40)))
    ds_feed.finish()
    for i in range(3):
        idx_feed.send(IoData.from_scalar(i))

    for sl, fu in zip(slice_log, full_log):
        assert sl.meta["window_start"] == fu.meta["window_start"]
        assert sl.meta["window_end"]   == fu.meta["window_end"]


# ── Metadata preservation ─────────────────────────────────────────────────────


def test_attrs_are_copied_into_each_emitted_slice() -> None:
    """Sliding doesn't strip ``units`` / ``sample_rate`` — downstream
    PlotSeries / Hodogram still get axis labels and time scales."""
    node = SlidingWindow()
    node.window_size = 5
    node.step = 5

    ds_feed, idx_feed, slice_log, _ = _wire(node)
    node.before_run()

    ds_feed.send(IoData.from_dataset(_make_df(20)))
    ds_feed.finish()
    idx_feed.send(IoData.from_scalar(0))

    assert slice_log[0].payload.attrs["sample_rate"] == 100.0
    assert slice_log[0].payload.attrs["units"] == {"value": "m/s"}


def test_slice_does_not_mutate_source_dataframe() -> None:
    """The held DATASET is shared across many ticks — make sure
    SlidingWindow doesn't accidentally mutate it."""
    df = _make_df(20)
    df_snapshot = df.copy()

    node = SlidingWindow()
    node.window_size = 5
    node.step = 5

    ds_feed, idx_feed, _, _ = _wire(node)
    node.before_run()

    ds_feed.send(IoData.from_dataset(df))
    ds_feed.finish()
    for i in range(3):
        idx_feed.send(IoData.from_scalar(i))

    pd.testing.assert_frame_equal(df, df_snapshot)

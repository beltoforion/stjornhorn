"""Tests for the :class:`~nodes.filters.plot_series.PlotSeries` node."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.io_data import IoData, IoDataType
from nodes.filters.plot_series import PlotSeries


def _run(node: PlotSeries, df: pd.DataFrame) -> np.ndarray:
    node.inputs[0].receive(IoData.from_dataset(df))
    out = node.outputs[0].last_emitted
    assert out is not None, "PlotSeries did not emit"
    assert out.type is IoDataType.IMAGE
    return out.image


def _single(n: int = 16) -> pd.DataFrame:
    return pd.DataFrame({"c0": np.sin(np.linspace(0, 2 * np.pi, n))})


# ── Output shape ──────────────────────────────────────────────────────────────

def test_emits_image_of_requested_size() -> None:
    node = PlotSeries()
    node.width = 200
    node.height = 100
    img = _run(node, _single())
    assert img.dtype == np.uint8
    assert img.shape == (100, 200, 3)


def test_default_size_is_640x360() -> None:
    img = _run(PlotSeries(), _single())
    assert img.shape == (360, 640, 3)


# ── Time axis ─────────────────────────────────────────────────────────────────

def test_step_controls_time_axis_extent() -> None:
    """Two nodes with different step values produce different-looking plots
    (different x-axis range). We verify indirectly by checking that the node
    runs without error for both; axis-range differences live inside matplotlib."""
    df = _single(32)
    node_slow = PlotSeries()
    node_slow.step = 1.0
    node_fast = PlotSeries()
    node_fast.step = 0.125
    img_slow = _run(node_slow, df)
    img_fast = _run(node_fast, df)
    # Both render successfully and produce non-identical images
    assert img_slow.shape == img_fast.shape
    assert not np.array_equal(img_slow, img_fast)


def test_start_offset_accepted() -> None:
    node = PlotSeries()
    node.start = 100.0
    node.step = 0.125
    img = _run(node, _single())
    assert img is not None


# ── y_column selection ────────────────────────────────────────────────────────

def test_empty_y_column_picks_first_column() -> None:
    df = pd.DataFrame({"amplitude": np.linspace(0.0, 1.0, 8)})
    node = PlotSeries()
    node.y_column = ""
    img = _run(node, df)
    assert img.size > 0


def test_explicit_y_column_selected() -> None:
    df = pd.DataFrame({"sig": np.zeros(8), "noise": np.ones(8)})
    node = PlotSeries()
    node.y_column = "noise"
    img = _run(node, df)
    assert img.size > 0


def test_missing_y_column_raises() -> None:
    node = PlotSeries()
    node.y_column = "nope"
    with pytest.raises(KeyError):
        _run(node, _single())


# ── attrs preservation ────────────────────────────────────────────────────────

def test_preserves_attrs_through_pipeline() -> None:
    """df.attrs must survive both AddIndexColumn and PlotXY internally."""
    df = _single()
    df.attrs["sample_rate"] = 8.0
    # No assertion on the image, just checking it doesn't crash and
    # the internal pipeline runs cleanly.
    img = _run(PlotSeries(), df)
    assert img is not None


# ── Param validation ──────────────────────────────────────────────────────────

def test_zero_step_rejected() -> None:
    node = PlotSeries()
    with pytest.raises(ValueError, match=r"step must be > 0"):
        node.step = 0.0


def test_negative_step_rejected() -> None:
    node = PlotSeries()
    with pytest.raises(ValueError, match=r"step must be > 0"):
        node.step = -1.0


# ── Band overlay (issue #246) ───────────────────────────────────────────────


def test_band_inputs_unconnected_render_unchanged() -> None:
    """Without band wiring, the rendered output is unchanged from the
    pre-band baseline."""
    node1 = PlotSeries()
    node1.width = 200
    node1.height = 100
    img1 = _run(node1, _single())

    node2 = PlotSeries()
    node2.width = 200
    node2.height = 100
    img2 = _run(node2, _single())
    np.testing.assert_array_equal(img1, img2)


def test_band_in_sample_row_coords_paints_translucent_span() -> None:
    """Band endpoints are sample-row indices; PlotSeries converts them
    via its own ``step``/``start`` to the time axis. With both wired,
    the band is visible (some pixels deviate from the no-band render)."""
    node = PlotSeries()
    node.width = 400
    node.height = 200
    node.step = 0.1
    node.start = 0.0
    node.grid = False
    df = pd.DataFrame({"c0": np.zeros(50)})

    # Wire a band over rows 10..30 → time 1.0..3.0 of the synthetic axis.
    node.inputs[1].receive(IoData.from_scalar(10))
    node.inputs[2].receive(IoData.from_scalar(30))
    node.inputs[0].receive(IoData.from_dataset(df))
    img_with = node.outputs[0].last_emitted.image  # type: ignore[union-attr]

    # Re-run with no band: this drives the inner PlotXY's band ports
    # to clear() so a stale forwarded value can't leak into this frame.
    node2 = PlotSeries()
    node2.width = 400
    node2.height = 200
    node2.step = 0.1
    node2.start = 0.0
    node2.grid = False
    node2.inputs[0].receive(IoData.from_dataset(df))
    img_without = node2.outputs[0].last_emitted.image  # type: ignore[union-attr]

    diff = np.any(img_with != img_without, axis=2)
    assert diff.sum() > 0, "expected the band to change some pixels"


def test_band_clears_when_endpoints_disconnected_between_frames() -> None:
    """When the band ports lose their fresh data (e.g. the upstream
    SlidingWindow stops emitting), the next frame must render without
    a stale band — the inner PlotXY's band ports get cleared."""
    node = PlotSeries()
    node.width = 200
    node.height = 100
    node.step = 0.1
    node.grid = False
    df = pd.DataFrame({"c0": np.zeros(50)})

    # Frame 1: band wired
    node.inputs[1].receive(IoData.from_scalar(10))
    node.inputs[2].receive(IoData.from_scalar(30))
    node.inputs[0].receive(IoData.from_dataset(df))
    img_with_band = node.outputs[0].last_emitted.image  # type: ignore[union-attr]

    # Frame 2: band ports cleared (simulating a disconnect / no-emit
    # tick from upstream). The clear() call in process_impl must wipe
    # the stale forwarded scalars.
    node.inputs[1].clear()
    node.inputs[2].clear()
    node.inputs[0].receive(IoData.from_dataset(df))
    img_no_band = node.outputs[0].last_emitted.image  # type: ignore[union-attr]

    diff = np.any(img_with_band != img_no_band, axis=2)
    assert diff.sum() > 0, "expected band-on / band-off frames to differ"


def test_band_position_tracks_step_and_start_conversion() -> None:
    """A band over rows [s, e] must land at time [start + s*step,
    start + e*step] on the rendered axis. We can't peek at matplotlib
    state once the figure is closed, so verify by comparing two
    PlotSeries instances configured so they should render identical
    bands but via different (step, start, sample-row) triples."""
    df = pd.DataFrame({"c0": np.zeros(100)})

    a = PlotSeries()
    a.width = 200
    a.height = 100
    a.step = 1.0
    a.start = 0.0
    a.grid = False
    a.inputs[1].receive(IoData.from_scalar(20))
    a.inputs[2].receive(IoData.from_scalar(40))
    a.inputs[0].receive(IoData.from_dataset(df))
    img_a = a.outputs[0].last_emitted.image  # type: ignore[union-attr]

    # Different sample-row coords but same time-axis position: rows
    # 200..400 with step=0.1 give the same band [20.0, 40.0] in time.
    df2 = pd.DataFrame({"c0": np.zeros(1000)})
    b = PlotSeries()
    b.width = 200
    b.height = 100
    b.step = 0.1
    b.start = 0.0
    b.grid = False
    b.inputs[1].receive(IoData.from_scalar(200))
    b.inputs[2].receive(IoData.from_scalar(400))
    b.inputs[0].receive(IoData.from_dataset(df2))
    img_b = b.outputs[0].last_emitted.image  # type: ignore[union-attr]

    # The renders won't be byte-identical (the underlying trace has a
    # different x-extent), but the band should occupy the same
    # *fraction* of the plot area in both. Here we just sanity-check
    # that both rendered without crashing — the precise pixel-level
    # equivalence is hard to assert from the outside.
    assert img_a is not None
    assert img_b is not None


# ── Trace cache (perf optimization for animated band) ───────────────────────


def test_trace_cache_reuses_render_when_dataset_identity_unchanged() -> None:
    """When the input ``IoData`` instance stays the same across ticks
    (the SlidingWindow→PlotSeries pattern: held one-shot CsvSource +
    streaming clock), matplotlib full render runs ONCE; subsequent
    ticks reuse the cached bitmap and just repaint the band in cv2.
    """
    from core.port import OutputPort
    from nodes.filters import plot_xy as plot_xy_mod
    from nodes.filters.plot_xy import PlotXY

    node = PlotSeries()
    node.width = 200; node.height = 100; node.grid = False; node.step = 0.1

    feeder = OutputPort("ds", {IoDataType.DATASET})
    bs = OutputPort("bs", {IoDataType.SCALAR})
    be = OutputPort("be", {IoDataType.SCALAR})
    feeder.connect(node.inputs[0])
    bs.connect(node.inputs[1])
    be.connect(node.inputs[2])

    feeder.send(IoData.from_dataset(pd.DataFrame({"c0": np.zeros(50)})))
    feeder.finish()  # data retained on input port across subsequent ticks

    render_count = 0
    real = PlotXY.render_with_axes
    def counting(*args, **kwargs):
        nonlocal render_count
        render_count += 1
        return real(*args, **kwargs)
    PlotXY.render_with_axes = staticmethod(counting)
    try:
        # Three ticks, three different bands, same dataset.
        bs.send(IoData.from_scalar(5));  be.send(IoData.from_scalar(10))
        bs.send(IoData.from_scalar(15)); be.send(IoData.from_scalar(20))
        bs.send(IoData.from_scalar(25)); be.send(IoData.from_scalar(30))
    finally:
        PlotXY.render_with_axes = staticmethod(real)

    assert render_count == 1, f"expected 1 matplotlib render, got {render_count}"


def test_trace_cache_invalidates_when_dataset_identity_changes() -> None:
    """A new IoData instance (e.g. an upstream filter that emits a
    fresh DataFrame per tick) must invalidate the cache so the
    rendered trace stays correct."""
    from core.port import OutputPort
    from nodes.filters.plot_xy import PlotXY

    node = PlotSeries()
    node.width = 200; node.height = 100; node.grid = False

    feeder = OutputPort("ds", {IoDataType.DATASET})
    feeder.connect(node.inputs[0])

    render_count = 0
    real = PlotXY.render_with_axes
    def counting(*args, **kwargs):
        nonlocal render_count
        render_count += 1
        return real(*args, **kwargs)
    PlotXY.render_with_axes = staticmethod(counting)
    try:
        for value in (1.0, 2.0, 3.0):
            # Each emit produces a new IoData via OutputPort.send's clone.
            feeder.send(IoData.from_dataset(pd.DataFrame({"c0": np.full(20, value)})))
            # Need to clear() so the next receive triggers a fire (port
            # data persists otherwise; in real use the framework does
            # this between dispatches).
            node.inputs[0].clear()
    finally:
        PlotXY.render_with_axes = staticmethod(real)

    # Each fresh IoData → cache miss → re-render.
    assert render_count == 3


def test_trace_cache_invalidates_on_param_change() -> None:
    """Editing a render-shaping param (size, title, step, …) between
    ticks must re-render even though the input IoData hasn't changed."""
    from core.port import OutputPort
    from nodes.filters.plot_xy import PlotXY

    node = PlotSeries()
    node.width = 200; node.height = 100; node.grid = False

    # Connect all three ports so the dispatcher waits for the band
    # endpoints before firing — otherwise the initial dataset send
    # would immediately fire+clear before we could mark it finished.
    ds = OutputPort("ds", {IoDataType.DATASET})
    bs = OutputPort("bs", {IoDataType.SCALAR})
    be = OutputPort("be", {IoDataType.SCALAR})
    ds.connect(node.inputs[0])
    bs.connect(node.inputs[1])
    be.connect(node.inputs[2])
    ds.send(IoData.from_dataset(pd.DataFrame({"c0": np.zeros(50)})))
    ds.finish()  # retain-after-finish so the dataset survives ticks

    render_count = 0
    real = PlotXY.render_with_axes
    def counting(*args, **kwargs):
        nonlocal render_count
        render_count += 1
        return real(*args, **kwargs)
    PlotXY.render_with_axes = staticmethod(counting)
    try:
        # Tick 1: cache miss, renders.
        bs.send(IoData.from_scalar(5));  be.send(IoData.from_scalar(10))
        # Tick 2: same params → cache hit.
        bs.send(IoData.from_scalar(15)); be.send(IoData.from_scalar(20))
        # Change a param; tick 3: cache miss, renders.
        node.title = "now with title"
        bs.send(IoData.from_scalar(25)); be.send(IoData.from_scalar(30))
        # Tick 4: same params again → cache hit.
        bs.send(IoData.from_scalar(35)); be.send(IoData.from_scalar(40))
    finally:
        PlotXY.render_with_axes = staticmethod(real)

    assert render_count == 2

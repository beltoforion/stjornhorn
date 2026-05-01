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


# ── Band overlay via IoMeta (issue #246) ─────────────────────────────────────


def _send(node: PlotSeries, df: pd.DataFrame, *,
          window_start: int | None = None,
          window_end:   int | None = None) -> np.ndarray:
    """Drive *node* with *df* (and an optional window meta-stamp) and
    return the emitted image. Mirrors the SlidingWindow → PlotSeries
    contract: window endpoints arrive as IoMeta keys."""
    from core.io_data import IoMeta
    meta = None
    if window_start is not None and window_end is not None:
        meta = IoMeta(window_start=window_start, window_end=window_end)
    node.inputs[0].receive(IoData.from_dataset(df, meta=meta))
    out = node.outputs[0].last_emitted
    assert out is not None
    return out.image


def test_no_window_meta_renders_without_band() -> None:
    """A dataset without ``window_start`` / ``window_end`` in its meta
    renders unchanged from the pre-band baseline."""
    node1 = PlotSeries()
    node1.width = 200
    node1.height = 100
    img1 = _send(node1, _single())

    node2 = PlotSeries()
    node2.width = 200
    node2.height = 100
    img2 = _send(node2, _single())
    np.testing.assert_array_equal(img1, img2)


def test_window_meta_paints_translucent_band() -> None:
    """``window_start`` / ``window_end`` keys (sample-row indices) on
    the input dataset's meta drive PlotSeries to overlay a band; the
    conversion to the synthesised time axis happens internally via
    ``step`` / ``start``."""
    node_with = PlotSeries()
    node_with.width = 400
    node_with.height = 200
    node_with.step = 0.1
    node_with.start = 0.0
    node_with.grid = False
    df = pd.DataFrame({"c0": np.zeros(50)})
    img_with = _send(node_with, df, window_start=10, window_end=30)

    node_without = PlotSeries()
    node_without.width = 400
    node_without.height = 200
    node_without.step = 0.1
    node_without.start = 0.0
    node_without.grid = False
    img_without = _send(node_without, df)

    diff = np.any(img_with != img_without, axis=2)
    assert diff.sum() > 0, "expected the band to change some pixels"


def test_band_disappears_when_meta_keys_drop_off_between_frames() -> None:
    """When the upstream stops stamping window meta (e.g. the
    SlidingWindow finishes), the next frame renders without a stale
    band — band logic re-checks meta on every frame."""
    node = PlotSeries()
    node.width = 200
    node.height = 100
    node.step = 0.1
    node.grid = False
    df = pd.DataFrame({"c0": np.zeros(50)})

    img_with    = _send(node, df, window_start=10, window_end=30)
    img_without = _send(node, df)  # same node — band must vanish

    diff = np.any(img_with != img_without, axis=2)
    assert diff.sum() > 0, "expected band-on / band-off frames to differ"


def test_partial_window_meta_does_not_render_band() -> None:
    """Only ``window_start`` (or only ``window_end``) on the meta is
    treated as no band — both must be present, parity with the
    explicit-port behaviour the M13 refactor replaced."""
    from core.io_data import IoMeta

    node_partial = PlotSeries()
    node_partial.width = 200; node_partial.height = 100; node_partial.grid = False
    node_partial.inputs[0].receive(IoData.from_dataset(
        pd.DataFrame({"c0": np.zeros(50)}),
        meta=IoMeta(window_start=10),
    ))
    img_partial = node_partial.outputs[0].last_emitted.image  # type: ignore[union-attr]

    node_baseline = PlotSeries()
    node_baseline.width = 200; node_baseline.height = 100; node_baseline.grid = False
    node_baseline.inputs[0].receive(IoData.from_dataset(pd.DataFrame({"c0": np.zeros(50)})))
    img_baseline = node_baseline.outputs[0].last_emitted.image  # type: ignore[union-attr]

    np.testing.assert_array_equal(img_partial, img_baseline)


# ── Trace cache (perf optimization for animated band) ───────────────────────


def test_trace_cache_reuses_render_when_dataframe_identity_unchanged() -> None:
    """The SlidingWindow → PlotSeries passthrough wraps the *same*
    DataFrame in a fresh IoData every tick. PlotSeries' cache is keyed
    on ``id(payload)``, so matplotlib full-renders ONCE; subsequent
    ticks reuse the cached bitmap and just repaint the band in cv2.
    """
    from core.io_data import IoMeta
    from nodes.filters.plot_xy import PlotXY

    node = PlotSeries()
    node.width = 200; node.height = 100; node.grid = False; node.step = 0.1
    df = pd.DataFrame({"c0": np.zeros(50)})

    render_count = 0
    real = PlotXY.render_with_axes
    def counting(*args, **kwargs):
        nonlocal render_count
        render_count += 1
        return real(*args, **kwargs)
    PlotXY.render_with_axes = staticmethod(counting)
    try:
        # Three ticks, three different band positions, same DataFrame.
        for ws, we in ((5, 10), (15, 20), (25, 30)):
            node.inputs[0].receive(
                IoData.from_dataset(df, meta=IoMeta(window_start=ws, window_end=we)),
            )
    finally:
        PlotXY.render_with_axes = staticmethod(real)

    assert render_count == 1, f"expected 1 matplotlib render, got {render_count}"


def test_trace_cache_invalidates_when_dataframe_changes() -> None:
    """A different DataFrame (typical of an animated upstream like a
    shift filter) must invalidate the cache so the rendered trace
    stays correct."""
    from nodes.filters.plot_xy import PlotXY

    node = PlotSeries()
    node.width = 200; node.height = 100; node.grid = False

    render_count = 0
    real = PlotXY.render_with_axes
    def counting(*args, **kwargs):
        nonlocal render_count
        render_count += 1
        return real(*args, **kwargs)
    PlotXY.render_with_axes = staticmethod(counting)
    try:
        for value in (1.0, 2.0, 3.0):
            # New DataFrame each iteration → new id(payload) → cache miss.
            node.inputs[0].receive(
                IoData.from_dataset(pd.DataFrame({"c0": np.full(20, value)})),
            )
    finally:
        PlotXY.render_with_axes = staticmethod(real)

    assert render_count == 3


def test_trace_cache_invalidates_on_param_change() -> None:
    """Editing a render-shaping param (size, title, step, …) between
    ticks must re-render even though the input DataFrame hasn't
    changed."""
    from core.io_data import IoMeta
    from nodes.filters.plot_xy import PlotXY

    node = PlotSeries()
    node.width = 200; node.height = 100; node.grid = False
    df = pd.DataFrame({"c0": np.zeros(50)})

    def push(ws: int, we: int) -> None:
        node.inputs[0].receive(
            IoData.from_dataset(df, meta=IoMeta(window_start=ws, window_end=we)),
        )

    render_count = 0
    real = PlotXY.render_with_axes
    def counting(*args, **kwargs):
        nonlocal render_count
        render_count += 1
        return real(*args, **kwargs)
    PlotXY.render_with_axes = staticmethod(counting)
    try:
        push(5, 10)   # cache miss → renders
        push(15, 20)  # cache hit
        node.title = "now with title"
        push(25, 30)  # param change → cache miss → renders
        push(35, 40)  # cache hit
    finally:
        PlotXY.render_with_axes = staticmethod(real)

    assert render_count == 2

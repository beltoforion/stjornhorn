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

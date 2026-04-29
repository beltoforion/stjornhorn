"""Tests for the :class:`~nodes.filters.add_index_column.AddIndexColumn` node."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.io_data import IoData, IoDataType
from nodes.filters.add_index_column import AddIndexColumn


def _run(node: AddIndexColumn, df: pd.DataFrame) -> pd.DataFrame:
    """Drive the node once and return the emitted DataFrame."""
    node.inputs[0].receive(IoData.from_dataset(df))
    out = node.outputs[0].last_emitted
    assert out is not None, "AddIndexColumn did not emit"
    assert out.type is IoDataType.DATASET
    return out.payload


# ── Defaults ──────────────────────────────────────────────────────────────────

def test_default_index_is_zero_based_step_one() -> None:
    df = pd.DataFrame({"v": [10.0, 20.0, 30.0]})
    out = _run(AddIndexColumn(), df)
    assert list(out.columns) == ["index", "v"]
    np.testing.assert_array_equal(out["index"].to_numpy(), [0.0, 1.0, 2.0])
    np.testing.assert_array_equal(out["v"].to_numpy(), [10.0, 20.0, 30.0])


def test_index_is_inserted_at_position_zero() -> None:
    """PlotXY's default x_column='' picks the first column, so the
    new index has to be at index 0 for the renderer to find it
    automatically."""
    df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
    out = _run(AddIndexColumn(), df)
    assert out.columns[0] == "index"


# ── Custom name / start / step ────────────────────────────────────────────────

def test_custom_name() -> None:
    df = pd.DataFrame({"v": [1.0, 2.0]})
    node = AddIndexColumn()
    node.name = "t"
    out = _run(node, df)
    assert list(out.columns) == ["t", "v"]


def test_custom_start_and_step_produce_time_axis() -> None:
    """Setting step = 1 / sample_rate produces a time axis in seconds —
    the seismic use case."""
    df = pd.DataFrame({"amplitude": [0.0, 0.0, 0.0, 0.0]})
    node = AddIndexColumn()
    node.name = "t"
    node.start = 0.0
    node.step = 0.125  # 8 Hz sampling
    out = _run(node, df)
    np.testing.assert_allclose(out["t"].to_numpy(), [0.0, 0.125, 0.250, 0.375])


def test_nonzero_start_offset() -> None:
    df = pd.DataFrame({"v": [0, 0, 0]})
    node = AddIndexColumn()
    node.start = 100.0
    out = _run(node, df)
    np.testing.assert_array_equal(out["index"].to_numpy(), [100.0, 101.0, 102.0])


# ── attrs preservation ───────────────────────────────────────────────────────

def test_preserves_dataset_attrs() -> None:
    """The whole point of the DATASET payload is that metadata travels
    with the data. Filters must not silently strip ``df.attrs``."""
    df = pd.DataFrame({"v": [1.0, 2.0]})
    df.attrs["sample_rate"] = 8.0
    df.attrs["station"] = "EIB"
    df.attrs["source_path"] = "/tmp/something.csv"

    out = _run(AddIndexColumn(), df)

    assert out.attrs["sample_rate"] == 8.0
    assert out.attrs["station"] == "EIB"
    assert out.attrs["source_path"] == "/tmp/something.csv"


# ── Error paths ───────────────────────────────────────────────────────────────

def test_collision_with_existing_column_raises() -> None:
    df = pd.DataFrame({"index": [0, 1, 2], "v": [10.0, 20.0, 30.0]})
    node = AddIndexColumn()
    with pytest.raises(ValueError, match="already exists"):
        _run(node, df)


def test_zero_step_rejected_at_param_set() -> None:
    """``step`` is strictly positive — set on the descriptor, not at
    process time, so a misconfigured flow fails at edit time rather
    than mid-run."""
    node = AddIndexColumn()
    with pytest.raises(ValueError, match=r"step must be > 0"):
        node.step = 0.0


def test_negative_step_rejected() -> None:
    node = AddIndexColumn()
    with pytest.raises(ValueError, match=r"step must be > 0"):
        node.step = -1.0


# ── Edge cases ────────────────────────────────────────────────────────────────

def test_empty_dataframe_produces_empty_index() -> None:
    """An empty DataFrame still has columns; the new index column has
    zero rows. Doesn't crash; downstream renderers will handle the
    no-data case (or raise their own clear error)."""
    df = pd.DataFrame({"v": pd.Series([], dtype=float)})
    out = _run(AddIndexColumn(), df)
    assert list(out.columns) == ["index", "v"]
    assert len(out) == 0


def test_does_not_mutate_input_dataframe() -> None:
    """The node copies before inserting, so the upstream's DataFrame
    keeps its original shape — important when the same upstream feeds
    multiple downstream branches."""
    df = pd.DataFrame({"v": [1.0, 2.0, 3.0]})
    df.attrs["original"] = True
    original_columns = list(df.columns)

    _run(AddIndexColumn(), df)

    assert list(df.columns) == original_columns
    assert "index" not in df.columns

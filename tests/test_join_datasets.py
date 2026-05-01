"""Tests for the :class:`~nodes.filters.join_datasets.JoinDatasets` node."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.io_data import IoData, IoDataType
from core.port import OutputPort
from nodes.filters.join_datasets import JoinDatasets


def _feed(node: JoinDatasets, *dfs: pd.DataFrame) -> pd.DataFrame | None:
    """Wire fake upstream ports, send *dfs*, return the emitted DataFrame.

    JoinDatasets only fires when every *connected* input has data, so
    upstreams must be wired before any send() — mirrors the pattern in
    test_merge.py.
    """
    upstreams: list[tuple[OutputPort, IoData]] = []
    for i, df in enumerate(dfs):
        up = OutputPort(f"up_{i}", {IoDataType.DATASET})
        up.connect(node.inputs[i])
        upstreams.append((up, IoData.from_dataset(df)))
    for up, data in upstreams:
        up.send(data)
    out = node.outputs[0].last_emitted
    if out is None:
        return None
    assert out.type is IoDataType.DATASET
    return out.payload


# ── Basic join ────────────────────────────────────────────────────────────────

def test_two_inputs_merged_into_one_dataframe() -> None:
    df1 = pd.DataFrame({"N": [1.0, 2.0, 3.0]})
    df2 = pd.DataFrame({"E": [4.0, 5.0, 6.0]})
    result = _feed(JoinDatasets(), df1, df2)
    assert result is not None
    assert list(result.columns) == ["N", "E"]
    np.testing.assert_array_equal(result["N"].to_numpy(), [1.0, 2.0, 3.0])
    np.testing.assert_array_equal(result["E"].to_numpy(), [4.0, 5.0, 6.0])


def test_three_inputs_merged() -> None:
    df1 = pd.DataFrame({"N": [1.0]})
    df2 = pd.DataFrame({"E": [2.0]})
    df3 = pd.DataFrame({"Z": [3.0]})
    result = _feed(JoinDatasets(), df1, df2, df3)
    assert result is not None
    assert list(result.columns) == ["N", "E", "Z"]


# ── column_names rename ───────────────────────────────────────────────────────

def test_column_names_renames_first_column_of_each_input() -> None:
    """The seismic use-case: CsvSource emits 'c0'; rename to component names."""
    df1 = pd.DataFrame({"c0": [1.0, 2.0]})
    df2 = pd.DataFrame({"c0": [3.0, 4.0]})
    node = JoinDatasets()
    node.column_names = "N,E"
    result = _feed(node, df1, df2)
    assert result is not None
    assert list(result.columns) == ["N", "E"]


def test_partial_rename_only_renames_first_n() -> None:
    """Rename list shorter than inputs → tail inputs keep their names."""
    df1 = pd.DataFrame({"c0": [1.0]})
    df2 = pd.DataFrame({"c0": [2.0]})
    df3 = pd.DataFrame({"Z": [3.0]})
    node = JoinDatasets()
    node.column_names = "N,E"  # only 2 names for 3 inputs
    result = _feed(node, df1, df2, df3)
    assert result is not None
    assert list(result.columns) == ["N", "E", "Z"]


def test_rename_only_the_first_column_when_input_is_multi_column() -> None:
    """Only the first column of each input is renamed; extras pass through."""
    df1 = pd.DataFrame({"t": [0.0, 1.0], "c0": [10.0, 20.0]})
    df2 = pd.DataFrame({"amp": [5.0, 6.0]})
    node = JoinDatasets()
    node.column_names = "time,signal"
    result = _feed(node, df1, df2)
    assert result is not None
    assert "time" in result.columns
    assert "c0" in result.columns
    assert "signal" in result.columns


# ── attrs preservation ────────────────────────────────────────────────────────

def test_attrs_from_first_input_are_forwarded() -> None:
    df1 = pd.DataFrame({"N": [1.0]})
    df1.attrs["sample_rate"] = 8.0
    df1.attrs["station"] = "EIB"
    df2 = pd.DataFrame({"E": [2.0]})
    df2.attrs["sample_rate"] = 100.0  # different — ignored

    result = _feed(JoinDatasets(), df1, df2)
    assert result is not None
    assert result.attrs["sample_rate"] == 8.0
    assert result.attrs["station"] == "EIB"


# ── Error paths ───────────────────────────────────────────────────────────────

def test_collision_without_rename_raises() -> None:
    df1 = pd.DataFrame({"c0": [1.0]})
    df2 = pd.DataFrame({"c0": [2.0]})
    with pytest.raises(ValueError, match="collision"):
        _feed(JoinDatasets(), df1, df2)


def test_single_input_does_not_emit() -> None:
    """One dataset connected — second missing → node should not emit."""
    node = JoinDatasets()
    up = OutputPort("up_0", {IoDataType.DATASET})
    up.connect(node.inputs[0])
    up.send(IoData.from_dataset(pd.DataFrame({"c0": [1.0]})))
    assert node.outputs[0].last_emitted is None


# ── Topology ──────────────────────────────────────────────────────────────────

def test_has_nine_input_ports() -> None:
    """Backend always carries the full pool of nine ``dataset_i``
    ports; the editor hides the trailing unused rows."""
    node = JoinDatasets()
    assert [p.name for p in node.inputs] == [f"dataset_{i}" for i in range(1, 10)]


def test_show_only_used_inputs_is_set() -> None:
    assert JoinDatasets.SHOW_ONLY_USED_INPUTS is True


# ── Input mutation guard ──────────────────────────────────────────────────────

def test_does_not_mutate_input_dataframes() -> None:
    df1 = pd.DataFrame({"c0": [1.0, 2.0]})
    df2 = pd.DataFrame({"c0": [3.0, 4.0]})
    original_cols_1 = list(df1.columns)
    original_cols_2 = list(df2.columns)

    node = JoinDatasets()
    node.column_names = "N,E"
    _feed(node, df1, df2)

    assert list(df1.columns) == original_cols_1
    assert list(df2.columns) == original_cols_2

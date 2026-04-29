"""Tests for the :class:`~nodes.sources.csv_source.CsvSource` node."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from core.io_data import IoDataType
from nodes.sources.csv_source import CsvSource


def _run(node: CsvSource) -> pd.DataFrame:
    """Drive ``node.process()`` once and return the emitted DataFrame."""
    node.process()
    out = node.outputs[0].last_emitted
    assert out is not None, "CsvSource did not emit"
    assert out.type is IoDataType.DATASET
    return out.payload


def _write_csv(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


# ── Basic round-trip ──────────────────────────────────────────────────────────

def test_emits_dataset_for_simple_csv(tmp_path: Path) -> None:
    csv = _write_csv(tmp_path / "trace.csv", "t,Z\n0.0,1.0\n0.1,2.0\n0.2,3.0\n")
    node = CsvSource()
    node.file_path = str(csv)

    df = _run(node)

    assert list(df.columns) == ["t", "Z"]
    assert df.shape == (3, 2)
    assert df["Z"].tolist() == [1.0, 2.0, 3.0]


def test_source_path_recorded_in_attrs(tmp_path: Path) -> None:
    """Downstream nodes need to know where the data came from for
    error messages and UI captions; CsvSource stamps it into ``attrs``."""
    csv = _write_csv(tmp_path / "log.csv", "a,b\n1,2\n")
    node = CsvSource()
    node.file_path = str(csv)

    df = _run(node)

    assert df.attrs["source_path"] == str(csv)


# ── Header handling ───────────────────────────────────────────────────────────

def test_no_header_synthesizes_column_names(tmp_path: Path) -> None:
    csv = _write_csv(tmp_path / "raw.csv", "1,2,3\n4,5,6\n")
    node = CsvSource()
    node.file_path = str(csv)
    node.has_header = False

    df = _run(node)

    assert list(df.columns) == ["c0", "c1", "c2"]
    assert df.shape == (2, 3)


def test_with_header_takes_first_row_as_names(tmp_path: Path) -> None:
    csv = _write_csv(tmp_path / "named.csv", "voltage,current\n0.0,0.0\n1.0,0.001\n")
    node = CsvSource()
    node.file_path = str(csv)

    df = _run(node)

    assert list(df.columns) == ["voltage", "current"]
    assert len(df) == 2


# ── Delimiter handling ────────────────────────────────────────────────────────

def test_semicolon_delimiter(tmp_path: Path) -> None:
    csv = _write_csv(tmp_path / "eu.csv", "a;b\n1;2\n3;4\n")
    node = CsvSource()
    node.file_path = str(csv)
    node.delimiter = ";"

    df = _run(node)

    assert list(df.columns) == ["a", "b"]
    assert df.iloc[1].tolist() == [3, 4]


def test_tab_delimiter_via_backslash_t(tmp_path: Path) -> None:
    """The widget can't easily emit a real tab character, so the user
    types ``\\t`` literally and CsvSource expands the escape."""
    csv = _write_csv(tmp_path / "tsv.csv", "x\ty\n1\t2\n")
    node = CsvSource()
    node.file_path = str(csv)
    node.delimiter = "\\t"  # two-char string: backslash + t

    df = _run(node)

    assert list(df.columns) == ["x", "y"]
    assert df.iloc[0].tolist() == [1, 2]


# ── Decimal separator ─────────────────────────────────────────────────────────

def test_european_decimal_separator(tmp_path: Path) -> None:
    csv = _write_csv(tmp_path / "eu_dec.csv", "v;i\n0,5;1,25\n")
    node = CsvSource()
    node.file_path = str(csv)
    node.delimiter = ";"
    node.decimal = ","

    df = _run(node)

    assert df["v"].iloc[0] == pytest.approx(0.5)
    assert df["i"].iloc[0] == pytest.approx(1.25)


# ── Error paths ───────────────────────────────────────────────────────────────

def test_missing_file_raises_file_not_found(tmp_path: Path) -> None:
    node = CsvSource()
    node.file_path = str(tmp_path / "does_not_exist.csv")

    with pytest.raises(FileNotFoundError, match="CSV file not found"):
        node.process()


# ── Reactivity contract ───────────────────────────────────────────────────────

def test_is_reactive(tmp_path: Path) -> None:
    """File sources are one-shot: the editor re-runs the flow on any
    parameter edit, same UX as :class:`ImageSource`."""
    assert CsvSource().is_reactive is True

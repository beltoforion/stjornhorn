"""Tests for :class:`~nodes.filters.spectrum.Spectrum`."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.io_data import IoData, IoDataType
from nodes.filters.spectrum import (
    INDEX_NAME_FREQUENCY,
    Spectrum,
    WindowKind,
)


def _run(node: Spectrum, df: pd.DataFrame) -> pd.DataFrame:
    node.inputs[0].receive(IoData.from_dataset(df))
    out = node.outputs[0].last_emitted
    assert out is not None
    assert out.type is IoDataType.DATASET
    return out.payload


# ── Output structure ─────────────────────────────────────────────────────────


def test_output_has_freq_index_and_same_columns() -> None:
    node = Spectrum()
    node.sample_rate = 8.0
    node.db_scale = False
    n = 64
    df = pd.DataFrame({"a": np.zeros(n), "b": np.zeros(n)})
    out = _run(node, df)
    assert list(out.columns) == ["a", "b"]
    assert out.index.name == INDEX_NAME_FREQUENCY
    assert out.shape == (n // 2 + 1, 2)
    np.testing.assert_allclose(
        out.index.to_numpy(),
        np.fft.rfftfreq(n, d=1.0 / 8.0),
        atol=1e-12,
    )


def test_attrs_are_propagated() -> None:
    node = Spectrum()
    df = pd.DataFrame({"a": np.zeros(64)})
    df.attrs["sample_rate"] = 8.0
    df.attrs["custom_key"] = "value"
    out = _run(node, df)
    assert out.attrs["sample_rate"] == 8.0
    assert out.attrs["custom_key"] == "value"


# ── Sinusoid math ────────────────────────────────────────────────────────────


def test_pure_sinusoid_peaks_at_its_frequency() -> None:
    fs = 8.0
    n = 256
    f0 = 1.0
    t = np.arange(n) / fs
    node = Spectrum()
    node.sample_rate = fs
    node.db_scale = False
    node.window = WindowKind.NONE
    df = pd.DataFrame({"sig": np.sin(2 * np.pi * f0 * t)})
    out = _run(node, df)
    peak_idx = int(out["sig"].to_numpy().argmax())
    peak_freq = float(out.index[peak_idx])
    assert peak_freq == pytest.approx(f0, abs=fs / n)


def test_freq_max_clips_the_output_range() -> None:
    fs = 8.0
    n = 64
    node = Spectrum()
    node.sample_rate = fs
    node.freq_max = 2.0
    df = pd.DataFrame({"sig": np.zeros(n)})
    out = _run(node, df)
    assert float(out.index.max()) <= 2.0
    # Should still contain frequencies up to but not exceeding 2 Hz.
    assert float(out.index.max()) > 1.5


def test_hann_window_changes_output_versus_none() -> None:
    """Sanity check that the window param actually drives the math."""
    fs = 8.0
    n = 128
    t = np.arange(n) / fs
    df = pd.DataFrame({"sig": np.sin(2 * np.pi * 1.0 * t)})

    node_hann = Spectrum()
    node_hann.sample_rate = fs
    node_hann.db_scale = False
    node_hann.window = WindowKind.HANN
    out_hann = _run(node_hann, df)

    node_none = Spectrum()
    node_none.sample_rate = fs
    node_none.db_scale = False
    node_none.window = WindowKind.NONE
    out_none = _run(node_none, df)

    assert not np.allclose(out_hann["sig"].to_numpy(), out_none["sig"].to_numpy())


# ── dB conversion ────────────────────────────────────────────────────────────


def test_db_floor_keeps_silent_cells_finite() -> None:
    fs = 8.0
    n = 32
    node = Spectrum()
    node.sample_rate = fs
    node.db_scale = True
    df = pd.DataFrame({"sig": np.zeros(n)})
    out = _run(node, df)
    assert np.all(np.isfinite(out["sig"].to_numpy()))


def test_db_peak_is_zero_for_unit_peak() -> None:
    """A spectrum whose peak magnitude is 1 should map to 0 dB."""
    node = Spectrum()
    out = pd.DataFrame(Spectrum._to_db(np.array([[1.0, 0.5], [0.0, 0.0]])))
    assert out.iloc[0, 0] == pytest.approx(0.0, abs=1e-9)


# ── Edge cases ───────────────────────────────────────────────────────────────


def test_too_short_input_emits_empty_frame() -> None:
    node = Spectrum()
    out = _run(node, pd.DataFrame({"sig": [1.0]}))
    assert out.shape == (0, 1)
    assert out.index.name == INDEX_NAME_FREQUENCY


def test_multi_column_input_processes_each_column_independently() -> None:
    fs = 8.0
    n = 128
    t = np.arange(n) / fs
    node = Spectrum()
    node.sample_rate = fs
    node.db_scale = False
    node.window = WindowKind.NONE
    df = pd.DataFrame({
        "f1": np.sin(2 * np.pi * 1.0 * t),
        "f2": np.sin(2 * np.pi * 2.0 * t),
    })
    out = _run(node, df)
    peak_f1 = float(out.index[int(out["f1"].to_numpy().argmax())])
    peak_f2 = float(out.index[int(out["f2"].to_numpy().argmax())])
    assert peak_f1 == pytest.approx(1.0, abs=fs / n)
    assert peak_f2 == pytest.approx(2.0, abs=fs / n)

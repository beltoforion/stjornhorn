"""Tests for :class:`~nodes.filters.polar_spectrum.PolarSpectrum`.

Focused on:

* the FFT / rotation math (``_compute_spectrum``, pure helper —
  testable without matplotlib);
* the dB conversion floor;
* the rendering pipeline emits an image of the requested shape and
  doesn't leak figures.

The visual correctness of the polar heatmap (cell layout, theta=N
convention) is verified indirectly: synthetic data with motion along
a known azimuth must produce its peak power at that azimuth.
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from core.io_data import IoData, IoDataType
from nodes.filters.polar_spectrum import PolarSpectrum


def _two_channel_df(x: np.ndarray, y: np.ndarray) -> pd.DataFrame:
    return pd.DataFrame({"N": x, "E": y})


def _run(node: PolarSpectrum, df: pd.DataFrame) -> np.ndarray:
    """Feed *df* into the node and return the emitted BGR image."""
    node.inputs[0].receive(IoData.from_dataset(df))
    out = node.outputs[0].last_emitted
    assert out is not None, "PolarSpectrum did not emit"
    assert out.type is IoDataType.IMAGE
    return out.image


# ── Output shape & lifecycle ─────────────────────────────────────────────────


def test_emits_image_of_requested_shape() -> None:
    node = PolarSpectrum()
    node.width = 200
    node.height = 200
    n = 64
    t = np.arange(n) / 8.0
    img = _run(node, _two_channel_df(np.sin(2 * np.pi * t), np.zeros(n)))

    assert img.dtype == np.uint8
    assert img.ndim == 3
    assert img.shape[:2] == (200, 200)


def test_no_open_figures_after_render() -> None:
    plt.close("all")
    node = PolarSpectrum()
    node.width = 200
    node.height = 200
    n = 64
    t = np.arange(n) / 8.0
    for _ in range(3):
        _run(node, _two_channel_df(np.sin(2 * np.pi * t), np.zeros(n)))
    assert plt.get_fignums() == [], "PolarSpectrum left matplotlib figures open"


def test_too_short_input_emits_blank_canvas() -> None:
    """An FFT of < 4 samples is meaningless; the node emits a blank
    canvas of the configured size so a downstream Mosaic or VideoSink
    doesn't see a frame-shape change between empty and populated
    windows."""
    node = PolarSpectrum()
    node.width = 100
    node.height = 100
    img = _run(node, _two_channel_df(np.array([1.0, 2.0]), np.array([0.5, 0.7])))
    assert img.shape[:2] == (100, 100)


# ── Pure spectrum math ───────────────────────────────────────────────────────


def test_compute_spectrum_shape_matches_n_angles_and_rfft_size() -> None:
    """``spec`` shape is ``(n_angles, n_freq)`` with
    ``n_freq = n // 2 + 1`` for an even-length input."""
    n = 128
    n_angles = 36
    x = np.zeros(n)
    y = np.zeros(n)
    thetas, freqs, spec = PolarSpectrum._compute_spectrum(x, y, 8.0, n_angles)
    assert thetas.shape == (n_angles,)
    assert freqs.shape  == (n // 2 + 1,)
    assert spec.shape   == (n_angles, n // 2 + 1)


def test_motion_along_x_axis_peaks_at_theta_zero_and_pi() -> None:
    """Pure x-axis motion (y = 0) projects fully onto θ=0 and θ=π
    (the rotation ``cos θ`` is ±1 there); orthogonal angles project to
    zero. The polar spectrum's peak power at the signal's frequency
    must therefore land on θ ∈ {0, π} and be near-zero at θ = π/2,
    3π/2."""
    fs   = 8.0
    n    = 128
    f0   = 1.0
    t    = np.arange(n) / fs
    x    = np.sin(2 * np.pi * f0 * t)
    y    = np.zeros(n)
    n_angles = 72  # 5° resolution → cardinal angles fall on bins
    thetas, freqs, spec = PolarSpectrum._compute_spectrum(x, y, fs, n_angles)

    # Frequency bin closest to f0
    k = int(np.argmin(np.abs(freqs - f0)))
    power_at_f0 = spec[:, k]

    angle_step = 2 * np.pi / n_angles

    def angle_idx(theta: float) -> int:
        return int(round(theta / angle_step)) % n_angles

    east_west = max(power_at_f0[angle_idx(0.0)], power_at_f0[angle_idx(np.pi)])
    north_south = max(
        power_at_f0[angle_idx(np.pi / 2)],
        power_at_f0[angle_idx(3 * np.pi / 2)],
    )
    assert east_west > 10 * north_south, (
        f"x-axis motion should concentrate at θ ∈ {{0, π}}: "
        f"east_west={east_west:.3f}, north_south={north_south:.3f}"
    )


def test_motion_along_y_axis_peaks_at_theta_pi_over_2_and_3pi_over_2() -> None:
    """Symmetric to the x-axis test: pure y-axis motion peaks at the
    perpendicular azimuths."""
    fs   = 8.0
    n    = 128
    f0   = 1.0
    t    = np.arange(n) / fs
    x    = np.zeros(n)
    y    = np.sin(2 * np.pi * f0 * t)
    n_angles = 72
    thetas, freqs, spec = PolarSpectrum._compute_spectrum(x, y, fs, n_angles)

    k = int(np.argmin(np.abs(freqs - f0)))
    power_at_f0 = spec[:, k]
    angle_step = 2 * np.pi / n_angles
    def angle_idx(theta: float) -> int:
        return int(round(theta / angle_step)) % n_angles

    north_south = max(
        power_at_f0[angle_idx(np.pi / 2)],
        power_at_f0[angle_idx(3 * np.pi / 2)],
    )
    east_west = max(power_at_f0[angle_idx(0.0)], power_at_f0[angle_idx(np.pi)])
    assert north_south > 10 * east_west


def test_diagonal_motion_peaks_at_45_degree_azimuths() -> None:
    """Motion along the 45° / 225° diagonal (x = y) should peak at
    those azimuths and be near-zero at 135° / 315°."""
    fs = 8.0
    n  = 128
    f0 = 1.0
    t  = np.arange(n) / fs
    s  = np.sin(2 * np.pi * f0 * t)
    n_angles = 72
    thetas, freqs, spec = PolarSpectrum._compute_spectrum(s, s, fs, n_angles)

    k = int(np.argmin(np.abs(freqs - f0)))
    power_at_f0 = spec[:, k]
    angle_step = 2 * np.pi / n_angles
    def angle_idx(theta: float) -> int:
        return int(round(theta / angle_step)) % n_angles

    forty_five = max(
        power_at_f0[angle_idx(np.pi / 4)],
        power_at_f0[angle_idx(5 * np.pi / 4)],
    )
    one_thirty_five = max(
        power_at_f0[angle_idx(3 * np.pi / 4)],
        power_at_f0[angle_idx(7 * np.pi / 4)],
    )
    assert forty_five > 10 * one_thirty_five


# ── dB conversion ────────────────────────────────────────────────────────────


def test_db_floor_keeps_silent_cells_finite() -> None:
    """A spectrum cell that's zero in the linear domain becomes
    ``20 * log10(floor)`` rather than ``-inf`` — colormaps don't
    render ``-inf`` cleanly."""
    spec = np.array([[1.0, 0.0, 0.5], [0.0, 0.0, 0.0]])
    db = PolarSpectrum._to_db(spec)
    assert np.all(np.isfinite(db))
    # The peak in linear → 0 dB in our convention is `20 log10(1)`.
    assert db[0, 0] == pytest.approx(0.0, abs=1e-9)


def test_db_floor_is_relative_to_peak() -> None:
    """Scaling the input by a factor shifts the dB output by the
    same multiplier in dB (i.e. all cells get +20 log10(scale))
    EXCEPT the floored ones, which clip to peak * 1e-6 — so peak-to-
    floor distance stays at ``120 dB`` regardless of input scale."""
    spec = np.array([[2.5, 0.0]])
    db = PolarSpectrum._to_db(spec)
    spread = float(db[0, 0] - db[0, 1])
    assert spread == pytest.approx(120.0, abs=1e-6)


# ── Column resolution ───────────────────────────────────────────────────────


def test_explicit_column_names_are_used_when_provided() -> None:
    """A 3-column input with named overrides plots the named pair, not
    the first two."""
    node = PolarSpectrum()
    node.x_column = "ch_a"
    node.y_column = "ch_c"
    node.width = 100
    node.height = 100
    n = 64
    t = np.arange(n) / 8.0
    df = pd.DataFrame({
        "ch_a": np.sin(2 * np.pi * t),
        "ch_b": np.zeros(n),
        "ch_c": np.cos(2 * np.pi * t),
    })
    img = _run(node, df)
    # Just verifies the pair was resolved without raising; numerical
    # check belongs to ``_compute_spectrum`` tests above.
    assert img is not None


def test_unknown_column_raises_keyerror() -> None:
    node = PolarSpectrum()
    node.x_column = "missing"
    df = pd.DataFrame({"N": np.zeros(64), "E": np.zeros(64)})
    with pytest.raises(KeyError, match="missing"):
        node.inputs[0].receive(IoData.from_dataset(df))


def test_single_column_input_raises_keyerror() -> None:
    """Default y_column resolution falls through to ``default_index=1``;
    a one-column input can't supply that, so the node raises with a
    clear message rather than silently plotting nonsense."""
    node = PolarSpectrum()
    df = pd.DataFrame({"N": np.zeros(64)})
    with pytest.raises(KeyError, match="at least 2"):
        node.inputs[0].receive(IoData.from_dataset(df))

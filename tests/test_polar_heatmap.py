"""Tests for :class:`~nodes.filters.polar_heatmap.PolarHeatmap`."""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from core.io_data import IoData, IoDataType
from nodes.filters.directional_projection import ATTR_THETAS_RAD
from nodes.filters.polar_heatmap import PolarHeatmap


def _polar_df(
    n_angles: int = 8, n_radii: int = 16, *, fill: float = 0.0,
) -> pd.DataFrame:
    """Return a DataFrame with degree-suffix column names and a numeric
    index — the canonical input shape from
    DirectionalProjection → Spectrum."""
    angles_deg = np.linspace(0, 360, n_angles, endpoint=False)
    columns = [f"{a:.1f}°" for a in angles_deg]
    radii = np.arange(n_radii, dtype=np.float64)
    df = pd.DataFrame(
        np.full((n_radii, n_angles), fill, dtype=np.float64),
        columns=columns,
        index=pd.Index(radii, name="frequency_hz"),
    )
    df.attrs[ATTR_THETAS_RAD] = np.radians(angles_deg)
    return df


def _run(node: PolarHeatmap, df: pd.DataFrame) -> np.ndarray:
    node.inputs[0].receive(IoData.from_dataset(df))
    out = node.outputs[0].last_emitted
    assert out is not None
    assert out.type is IoDataType.IMAGE
    return out.image


# ── Output shape & lifecycle ─────────────────────────────────────────────────


def test_emits_image_of_requested_shape() -> None:
    node = PolarHeatmap()
    node.width = 200
    node.height = 200
    img = _run(node, _polar_df())
    assert img.dtype == np.uint8
    assert img.ndim == 3
    assert img.shape[:2] == (200, 200)


def test_no_open_figures_after_render() -> None:
    plt.close("all")
    node = PolarHeatmap()
    node.width = 200
    node.height = 200
    for _ in range(3):
        _run(node, _polar_df())
    assert plt.get_fignums() == [], "PolarHeatmap left matplotlib figures open"


def test_too_small_input_emits_blank_canvas() -> None:
    node = PolarHeatmap()
    node.width = 100
    node.height = 100
    df = pd.DataFrame({"0.0°": [1.0]})  # only one column, can't render a heatmap
    df.attrs[ATTR_THETAS_RAD] = np.array([0.0])
    img = _run(node, df)
    assert img.shape[:2] == (100, 100)


# ── Angle resolution ─────────────────────────────────────────────────────────


def test_thetas_attr_is_preferred_over_column_names() -> None:
    """When ``df.attrs[ATTR_THETAS_RAD]`` is set, columns may have any
    name and the attr drives the layout."""
    node = PolarHeatmap()
    node.width = 100
    node.height = 100
    df = pd.DataFrame(
        np.zeros((4, 3)),
        columns=["foo", "bar", "baz"],
        index=pd.Index(np.arange(4), name="r"),
    )
    df.attrs[ATTR_THETAS_RAD] = np.array([0.0, np.pi / 2, np.pi])
    img = _run(node, df)
    assert img.shape[:2] == (100, 100)


def test_column_name_parsing_falls_back_when_attr_missing() -> None:
    """Without the attr, columns named ``"5.0°"`` etc. parse cleanly."""
    node = PolarHeatmap()
    node.width = 100
    node.height = 100
    df = pd.DataFrame(
        np.zeros((4, 3)),
        columns=["0°", "120°", "240°"],
        index=pd.Index(np.arange(4), name="r"),
    )
    img = _run(node, df)
    assert img.shape[:2] == (100, 100)


def test_unparseable_column_name_raises() -> None:
    node = PolarHeatmap()
    df = pd.DataFrame(
        np.zeros((4, 3)),
        columns=["foo", "bar", "baz"],
        index=pd.Index(np.arange(4), name="r"),
    )
    with pytest.raises(ValueError, match="parse an angle"):
        node.inputs[0].receive(IoData.from_dataset(df))


def test_thetas_attr_with_wrong_length_raises() -> None:
    node = PolarHeatmap()
    df = pd.DataFrame(
        np.zeros((4, 3)),
        columns=["a", "b", "c"],
        index=pd.Index(np.arange(4), name="r"),
    )
    df.attrs[ATTR_THETAS_RAD] = np.array([0.0, 1.0])  # too short
    with pytest.raises(ValueError, match="expected"):
        node.inputs[0].receive(IoData.from_dataset(df))


def test_unsorted_thetas_render_correctly() -> None:
    """Columns may arrive in arbitrary angular order; the renderer
    sorts internally so the polar mesh wraps cleanly."""
    node = PolarHeatmap()
    node.width = 100
    node.height = 100
    df = pd.DataFrame(
        np.zeros((4, 4)),
        columns=["a", "b", "c", "d"],
        index=pd.Index(np.arange(4), name="r"),
    )
    df.attrs[ATTR_THETAS_RAD] = np.array(
        [np.pi, 0.0, 3 * np.pi / 2, np.pi / 2],
    )
    img = _run(node, df)
    assert img.shape[:2] == (100, 100)

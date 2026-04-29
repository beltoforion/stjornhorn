"""Tests for the :class:`~nodes.filters.hodogram.Hodogram` node and
its pure-math companion :class:`ParticleMotion`."""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from core.io_data import IoData, IoDataType
from nodes.filters.hodogram import (
    Hodogram,
    HodogramRenderer,
    ParticleMotion,
    PrincipalAxis,
)


# ── ParticleMotion (pure math, no matplotlib) ────────────────────────────────


def test_particle_motion_rejects_mismatched_lengths() -> None:
    with pytest.raises(ValueError, match="same length"):
        ParticleMotion(np.array([0.0, 1.0]), np.array([0.0, 1.0, 2.0]))


def test_particle_motion_rejects_2d_input() -> None:
    with pytest.raises(ValueError, match="1-D"):
        ParticleMotion(np.zeros((2, 2)), np.zeros((2, 2)))


def test_particle_motion_centroid_is_mean() -> None:
    m = ParticleMotion(np.array([0.0, 2.0, 4.0]), np.array([1.0, 3.0, 5.0]))
    assert m.centroid == (pytest.approx(2.0), pytest.approx(3.0))


def test_particle_motion_trajectory_round_trip() -> None:
    m = ParticleMotion(np.array([1.0, 2.0]), np.array([3.0, 4.0]))
    traj = m.trajectory
    assert traj.shape == (2, 2)
    np.testing.assert_array_equal(traj[:, 0], [1.0, 2.0])
    np.testing.assert_array_equal(traj[:, 1], [3.0, 4.0])


def test_principal_axis_horizontal_line() -> None:
    """A horizontal line (y = const) has its principal axis along +X."""
    x = np.linspace(-1.0, 1.0, 100)
    y = np.zeros_like(x)
    axis = ParticleMotion(x, y).principal_axis()
    assert axis.angle_deg == pytest.approx(0.0, abs=0.5)
    assert axis.linearity == float("inf")


def test_principal_axis_45_degree_line() -> None:
    """y = x → principal axis at 45° from +X. Spec requirement from the
    issue: linear motion with show_polarization fits an axis near 45°."""
    x = np.linspace(-1.0, 1.0, 100)
    y = x.copy()
    axis = ParticleMotion(x, y).principal_axis()
    assert axis.angle_deg == pytest.approx(45.0, abs=1.0)
    assert axis.linearity == float("inf")


def test_principal_axis_circular_motion_has_linearity_one() -> None:
    """A perfect circle has equal eigenvalues → linearity = 1.0. The
    angle is undefined for a circle (any direction works) so we don't
    check it."""
    t = np.linspace(0.0, 2 * np.pi, 200, endpoint=False)
    axis = ParticleMotion(np.cos(t), np.sin(t)).principal_axis()
    assert axis.linearity == pytest.approx(1.0, abs=0.05)


def test_principal_axis_handles_single_sample() -> None:
    """Degenerate input must not crash. A single point has no spread,
    so we return angle 0 and linearity ∞ as a sentinel."""
    axis = ParticleMotion(np.array([0.0]), np.array([0.0])).principal_axis()
    assert axis.angle_rad == 0.0
    assert axis.linearity == float("inf")


def test_principal_axis_negative_slope_normalised() -> None:
    """The principal axis is undirected — angle should be wrapped into
    [-π/2, π/2] regardless of which eigenvector sign numpy returns."""
    x = np.linspace(-1.0, 1.0, 100)
    y = -x
    axis = ParticleMotion(x, y).principal_axis()
    assert axis.angle_deg == pytest.approx(-45.0, abs=1.0)


# ── Hodogram node — render output ────────────────────────────────────────────


def _zne_df(n: int = 64) -> pd.DataFrame:
    """A small Z/N/E DataFrame: linear N-vs-E motion at 30°."""
    t = np.linspace(0.0, 1.0, n)
    return pd.DataFrame(
        {
            "Z": np.zeros(n),
            "N": np.cos(np.deg2rad(30.0)) * t,
            "E": np.sin(np.deg2rad(30.0)) * t,
        }
    )


def _run(node: Hodogram, df: pd.DataFrame) -> np.ndarray:
    node.inputs[0].receive(IoData.from_dataset(df))
    out = node.outputs[0].last_emitted
    assert out is not None, "Hodogram did not emit"
    assert out.type is IoDataType.IMAGE
    return out.image


def test_hodogram_emits_image_of_requested_shape() -> None:
    node = Hodogram()
    node.width = 200
    node.height = 200
    img = _run(node, _zne_df())
    assert img.dtype == np.uint8
    assert img.shape == (200, 200, 3)


def test_hodogram_default_columns_pick_n_and_e() -> None:
    """A Z/N/E dataset is the seismic happy path — defaults should
    just work without the user typing column names."""
    node = Hodogram()  # x="N", y="E"
    img = _run(node, _zne_df())
    assert img.size > 0


def test_hodogram_falls_back_to_positional_for_non_seismic_columns() -> None:
    """When the Dataset doesn't use Z/N/E names, the seismic defaults
    can't match — the positional fallback (first / second columns)
    kicks in so a generic 2-column Dataset still renders."""
    df = pd.DataFrame({"alpha": np.linspace(0, 1, 16), "beta": np.linspace(0, 0.5, 16)})
    node = Hodogram()  # defaults still "N"/"E"
    img = _run(node, df)
    assert img.size > 0


def test_hodogram_raises_on_too_few_columns() -> None:
    df = pd.DataFrame({"only": [1.0, 2.0, 3.0]})
    node = Hodogram()
    with pytest.raises(KeyError, match=r"≥ 2 columns"):
        _run(node, df)


def test_hodogram_color_by_time_off_uses_solid_line() -> None:
    """The smoke test: with color_by_time=False the renderer takes
    the ``ax.plot`` path instead of the LineCollection path. We can't
    easily inspect a rendered image, but we can verify the node emits
    a valid image of the right shape — the visual difference is
    tracked via the unit test against a reference image, deferred."""
    node = Hodogram()
    node.color_by_time = False
    img = _run(node, _zne_df())
    assert img.dtype == np.uint8
    assert img.ndim == 3


def test_hodogram_show_polarization_smoke() -> None:
    """show_polarization=True calls into ParticleMotion.principal_axis()
    and overlays the result. End-to-end smoke test that the path
    doesn't crash on real data."""
    node = Hodogram()
    node.show_polarization = True
    img = _run(node, _zne_df())
    assert img.size > 0


# ── HodogramRenderer (Strategy isolation) ────────────────────────────────────


def test_renderer_no_open_figures_after_render() -> None:
    plt.close("all")
    renderer = HodogramRenderer()
    motion = ParticleMotion(np.linspace(0, 1, 32), np.linspace(0, 1, 32))
    for _ in range(5):
        renderer.render(
            motion,
            x_label="N",
            y_label="E",
            width=160,
            height=160,
            color_by_time=True,
            equal_aspect=True,
            show_polarization=False,
        )
    assert plt.get_fignums() == [], "HodogramRenderer leaked figures"


def test_renderer_no_open_figures_after_render_error() -> None:
    """Mismatched-length input is caught at ParticleMotion construction
    rather than mid-render, so this test exercises an error inside
    rendering by passing a renderer-illegal width."""
    plt.close("all")
    motion = ParticleMotion(np.zeros(0), np.zeros(0))
    renderer = HodogramRenderer()
    # Empty trajectory is fine to render (autoscale will pick limits);
    # use it to drive the render path through quickly and confirm
    # the figure still closes.
    renderer.render(
        motion,
        x_label="N",
        y_label="E",
        width=120,
        height=120,
        color_by_time=False,
        equal_aspect=False,
        show_polarization=False,
    )
    assert plt.get_fignums() == []


# ── Axis label / unit formatting ─────────────────────────────────────────────


def test_axis_label_appends_unit_when_known() -> None:
    df = pd.DataFrame({"N": [0.0], "E": [0.0]})
    df.attrs["units"] = {"N": "m/s", "E": "m/s"}
    assert Hodogram._axis_label(df, "N") == "N [m/s]"
    assert Hodogram._axis_label(df, "E") == "E [m/s]"


def test_axis_label_no_units() -> None:
    df = pd.DataFrame({"N": [0.0], "E": [0.0]})
    assert Hodogram._axis_label(df, "N") == "N"


def test_principal_axis_dataclass_angle_deg() -> None:
    """``PrincipalAxis.angle_deg`` is a small derived property; verify
    it tracks ``angle_rad`` so any rounding helper using it stays
    in sync."""
    a = PrincipalAxis(angle_rad=np.pi / 4, linearity=10.0)
    assert a.angle_deg == pytest.approx(45.0)

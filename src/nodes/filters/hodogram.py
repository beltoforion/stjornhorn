from __future__ import annotations

# Switch matplotlib to the off-screen Agg backend BEFORE pyplot is
# imported anywhere in the module, so figure rendering stays
# self-contained and doesn't claim the host editor's Qt backend.
import matplotlib

matplotlib.use("Agg")

from dataclasses import dataclass

import cv2
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.collections import LineCollection
from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase
from core.params import BoolParam, IntParam, StringParam
from core.port import InputPort, OutputPort

#: Render DPI used when sizing the matplotlib figure. Width / height in
#: pixels are converted to inches via ``size_px / _RENDER_DPI``.
_RENDER_DPI: int = 100

#: Default colormap for the time-coloured trajectory. Viridis is
#: perceptually uniform so the time-direction reads correctly even on
#: a colour-blind display.
_TIME_COLORMAP: str = "viridis"

#: Length of the principal-axis overlay relative to the data extent.
#: 0.75 of the diagonal extends well past the trajectory at both ends
#: so the fitted axis is unambiguous to read.
_POLARIZATION_AXIS_FACTOR: float = 0.75


# ── Pure-math: 2-D particle motion ───────────────────────────────────────────


@dataclass(frozen=True)
class PrincipalAxis:
    """Result of fitting a principal axis through a 2-D trajectory."""

    #: Angle of the principal eigenvector measured CCW from the +X axis,
    #: normalised into ``[-π/2, π/2]`` since direction sign is arbitrary
    #: (the axis is undirected).
    angle_rad: float

    #: Ratio of the larger to the smaller eigenvalue. ``1.0`` indicates
    #: isotropic (circular) motion; ``∞`` perfectly linear motion.
    linearity: float

    @property
    def angle_deg(self) -> float:
        return float(np.degrees(self.angle_rad))


class ParticleMotion:
    """2-D particle motion described by paired X / Y sample arrays.

    Pure-math companion to :class:`HodogramRenderer` — kept matplotlib-free
    so the geometric content (trajectory, centroid, fitted polarization
    axis) is testable in isolation. The renderer uses this class as
    its data source via the :class:`HodogramRenderer.render` Strategy
    method.

    Both arrays must be 1-D and the same length. Order is preserved so
    a downstream renderer can colour each segment by its time index.
    """

    def __init__(self, x: np.ndarray, y: np.ndarray) -> None:
        x_arr = np.asarray(x)
        y_arr = np.asarray(y)
        if x_arr.ndim != 1 or y_arr.ndim != 1:
            raise ValueError(
                f"ParticleMotion expects 1-D arrays; got shapes "
                f"{x_arr.shape} and {y_arr.shape}"
            )
        if x_arr.shape != y_arr.shape:
            raise ValueError(
                f"ParticleMotion x and y must have the same length; "
                f"got {x_arr.size} vs {y_arr.size}"
            )
        self._x = x_arr.astype(float, copy=False)
        self._y = y_arr.astype(float, copy=False)

    @property
    def trajectory(self) -> np.ndarray:
        """Return the trajectory as an ``Nx2`` array of ``(x, y)`` pairs."""
        return np.column_stack([self._x, self._y])

    @property
    def centroid(self) -> tuple[float, float]:
        """``(mean_x, mean_y)`` — used as the anchor for the fitted axis."""
        return float(np.mean(self._x)), float(np.mean(self._y))

    @property
    def n_samples(self) -> int:
        return int(self._x.size)

    def principal_axis(self) -> PrincipalAxis:
        """Fit a 2-D PCA axis through the centred trajectory.

        Eigen-decomposes the 2×2 sample covariance and returns the
        angle of the larger-eigenvalue eigenvector together with the
        eigenvalue ratio (linearity). For seismic Z/N/E plotted as
        N-vs-E, ``angle_rad`` measured from the +X axis equals the
        polarisation azimuth; for non-seismic data it's just the
        principal direction of the cloud.

        Falls back gracefully on degenerate inputs:
        * fewer than 2 samples → angle 0, linearity ``inf`` (no spread).
        * zero variance along the minor axis → linearity ``inf``.
        """
        if self.n_samples < 2:
            return PrincipalAxis(angle_rad=0.0, linearity=float("inf"))

        cx, cy = self.centroid
        dx = self._x - cx
        dy = self._y - cy
        # ``np.cov`` divides by ``N-1`` by default; the eigen problem
        # is invariant under a positive scalar so the divisor doesn't
        # affect the angle / ratio we extract here.
        cov = np.cov(np.vstack([dx, dy]))
        eigvals, eigvecs = np.linalg.eigh(cov)  # ascending eigenvalues
        idx_major = int(np.argmax(eigvals))
        idx_minor = 1 - idx_major
        v = eigvecs[:, idx_major]
        angle = float(np.arctan2(v[1], v[0]))
        # Wrap into [-π/2, π/2]: the axis is undirected so
        # ``angle`` and ``angle + π`` describe the same orientation.
        if angle > np.pi / 2:
            angle -= np.pi
        elif angle < -np.pi / 2:
            angle += np.pi

        major = float(eigvals[idx_major])
        minor = float(eigvals[idx_minor])
        linearity = float("inf") if minor <= 0 else major / minor
        return PrincipalAxis(angle_rad=angle, linearity=linearity)


# ── Off-screen renderer (Strategy) ───────────────────────────────────────────


class HodogramRenderer:
    """Render a :class:`ParticleMotion` as a particle-motion plot.

    Strategy split from :class:`Hodogram` so a future variant
    (animated, 3-D, log-scale) can be dropped in without touching
    the node. Always closes the matplotlib figure on exit so
    long-running flows don't leak figures across frames.
    """

    def render(
        self,
        motion: ParticleMotion,
        *,
        x_label: str,
        y_label: str,
        width: int,
        height: int,
        color_by_time: bool,
        equal_aspect: bool,
        show_polarization: bool,
        title: str = "",
    ) -> np.ndarray:
        fig = plt.figure(
            figsize=(width / _RENDER_DPI, height / _RENDER_DPI),
            dpi=_RENDER_DPI,
        )
        try:
            ax = fig.add_subplot(111)
            traj = motion.trajectory

            if color_by_time and motion.n_samples >= 2:
                # LineCollection lets us colour each segment by its
                # position in time without per-segment matplotlib calls
                # (which would dominate runtime for long traces).
                segments = np.stack([traj[:-1], traj[1:]], axis=1)
                t = np.linspace(0.0, 1.0, len(segments))
                lc = LineCollection(
                    segments, cmap=_TIME_COLORMAP, array=t, linewidth=1.0
                )
                ax.add_collection(lc)
                ax.autoscale_view()
            else:
                ax.plot(traj[:, 0], traj[:, 1], linewidth=1.0)

            if show_polarization and motion.n_samples >= 2:
                self._draw_polarization_overlay(ax, motion)

            ax.set_xlabel(x_label)
            ax.set_ylabel(y_label)
            if title:
                ax.set_title(title)
            if equal_aspect:
                ax.set_aspect("equal", adjustable="datalim")
            ax.grid(True, alpha=0.3)
            fig.tight_layout(pad=0.4)
            fig.canvas.draw()
            rgba = np.asarray(fig.canvas.buffer_rgba())
            return cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGR)
        finally:
            plt.close(fig)

    @staticmethod
    def _draw_polarization_overlay(ax, motion: ParticleMotion) -> None:
        """Overlay the fitted PCA axis through the centroid.

        Line length is a fixed multiple of the trajectory's diagonal
        extent so the axis extends visibly past the data on both
        sides regardless of scale.
        """
        axis = motion.principal_axis()
        cx, cy = motion.centroid
        traj = motion.trajectory
        x_span = float(np.ptp(traj[:, 0]))
        y_span = float(np.ptp(traj[:, 1]))
        half_length = _POLARIZATION_AXIS_FACTOR * float(np.hypot(x_span, y_span))
        dx = half_length * np.cos(axis.angle_rad)
        dy = half_length * np.sin(axis.angle_rad)
        ax.plot(
            [cx - dx, cx + dx],
            [cy - dy, cy + dy],
            color="red",
            linestyle="--",
            linewidth=1.2,
            label=f"axis: {axis.angle_deg:.1f}°, linearity {axis.linearity:.2f}",
        )
        ax.legend(loc="best", fontsize="small", framealpha=0.7)


# ── Node ──────────────────────────────────────────────────────────────────────


class Hodogram(NodeBase):
    """Render two columns of a :data:`IoDataType.DATASET` as a hodogram.

    A hodogram is a particle-motion plot — the trajectory of one signal
    against another instead of each one against time. The canonical use
    is seismic polarisation analysis (plot N-vs-E ground motion to
    estimate back-azimuth from a P-wave's linear arrival), but the same
    view is generic enough for Lissajous figures, phase-space loops, or
    any pair of correlated signals.

    Three visual options on top of the basic trajectory:

    * **Color-by-time** (default on) — colours each segment via the
      ``viridis`` colormap so the direction of travel reads as a
      gradient cool→warm.
    * **Equal aspect** (default on) — forces 1:1 axis scaling so the
      geometry (linear vs elliptical motion) is meaningful at a glance.
    * **Show polarization** (default off) — fits a 2-D PCA axis through
      the trajectory and overlays it; the legend reports the angle
      from +X and the linearity ratio. Off by default so the node
      stays generic for non-seismic use.

    Parameters:
      x_column          -- column name for X. Default ``"N"`` (the
                           seismic convention); falls back to the
                           first column when no ``"N"`` is present.
      y_column          -- column name for Y. Default ``"E"``; falls
                           back to the second column.
      width / height    -- output image size in pixels (≥ 64).
      color_by_time     -- gradient-colour the trajectory.
      equal_aspect      -- force 1:1 axis scaling.
      show_polarization -- overlay the fitted PCA axis + readout.
    """

    x_column = StringParam(
        "N",
        placeholder="N",
        description=(
            "Column name for the X axis. Default 'N' matches the "
            "standard seismic Z/N/E ordering; falls back to the first "
            "column when no 'N' is present."
        ),
    )
    y_column = StringParam(
        "E",
        placeholder="E",
        description=(
            "Column name for the Y axis. Default 'E'; falls back to "
            "the second column when no 'E' is present."
        ),
    )
    width = IntParam(
        360,
        min=64,
        unit="px",
        description="Output image width in pixels.",
    )
    height = IntParam(
        360,
        min=64,
        unit="px",
        description="Output image height in pixels.",
    )
    color_by_time = BoolParam(
        True,
        description=(
            "Colour each trajectory segment by its position in time "
            "via the viridis colormap. Off → single-colour trajectory."
        ),
    )
    equal_aspect = BoolParam(
        True,
        description=(
            "Force a 1:1 axis scale so the geometry (linear vs "
            "elliptical motion) is meaningful at a glance."
        ),
    )
    show_polarization = BoolParam(
        False,
        description=(
            "Fit a 2-D PCA axis through the trajectory and overlay "
            "it as a dashed red line. The legend shows the angle "
            "from +X and the linearity ratio."
        ),
    )
    title = StringParam(
        "",
        placeholder="(no title)",
        description="Optional plot title rendered above the axes.",
    )

    def __init__(self) -> None:
        super().__init__("Hodogram", section="Visualization")
        self._add_input(InputPort("dataset", {IoDataType.DATASET}))
        self._add_output(OutputPort("image", {IoDataType.IMAGE}))
        self._apply_default_params()

    @override
    def process_impl(self) -> None:
        df: pd.DataFrame = self.inputs[0].data.payload
        if len(df.columns) < 2:
            raise KeyError(
                f"Hodogram needs ≥ 2 columns; "
                f"dataset has {len(df.columns)}: {list(df.columns)}"
            )
        x_col = self._resolve_column(df, self._x_column, default_index=0)
        y_col = self._resolve_column(df, self._y_column, default_index=1)

        motion = ParticleMotion(df[x_col].to_numpy(), df[y_col].to_numpy())
        renderer = HodogramRenderer()
        bgr = renderer.render(
            motion,
            x_label=self._axis_label(df, x_col),
            y_label=self._axis_label(df, y_col),
            width=self._width,
            height=self._height,
            color_by_time=self._color_by_time,
            equal_aspect=self._equal_aspect,
            show_polarization=self._show_polarization,
            title=self._title,
        )
        self.outputs[0].send(IoData.from_image(bgr))

    # ── Pure helpers (testable without rendering) ────────────────────────────

    @staticmethod
    def _resolve_column(
        df: pd.DataFrame, requested: str, *, default_index: int
    ) -> str:
        """Resolve a column name with a positional fallback.

        Unlike :class:`PlotXY`, the empty-string case never arises here
        (the descriptor seeds ``"N"``/``"E"`` defaults). When the
        requested name *is* set but missing — typical for non-seismic
        Datasets that don't use Z/N/E names — the positional fallback
        kicks in instead of raising, so a default-configured Hodogram
        on a generic 2-column Dataset still renders.
        """
        if requested and requested in df.columns:
            return requested
        if default_index >= len(df.columns):
            raise KeyError(
                f"Cannot resolve column {requested!r}: "
                f"dataset has {len(df.columns)} column(s)"
            )
        return str(df.columns[default_index])

    @staticmethod
    def _axis_label(df: pd.DataFrame, column: str) -> str:
        """Compose an axis label, appending the column's unit when known.

        ``df.attrs["units"]`` is a ``{column: unit_string}`` dict
        populated by upstream nodes (``SetUnits``) or domain-aware
        sources. Missing entries yield a bare column-name label.
        """
        units = df.attrs.get("units")
        if isinstance(units, dict):
            unit = units.get(column)
            if unit:
                return f"{column} [{unit}]"
        return str(column)

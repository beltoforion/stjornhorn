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

#: Names of the two DATASET input ports — also used as the default
#: axis labels when the input dataset's first column is named with
#: a generic placeholder (CsvSource emits ``c0``).
_X_INPUT: str = "x"
_Y_INPUT: str = "y"

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
    """Render a :class:`ParticleMotion` as a particle-motion plot."""

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
    """Render two single-column :data:`IoDataType.DATASET` inputs as a hodogram.

    A hodogram is a particle-motion plot — the trajectory of one
    signal against another. Typical uses: seismic polarisation
    analysis (N vs E ground motion), Lissajous figures, phase-space
    loops. The first column of each input is used as the signal, so
    one single-column source per axis wires straight in.

    ``show_polarization`` overlays a 2-D PCA fit through the
    trajectory and reports the angle from +X and the linearity ratio.
    """

    x_label = StringParam(
        "",
        placeholder="(column name)",
        description=(
            "Override label for the X axis. Empty falls back to the "
            "column name of the x input's first column."
        ),
    )
    y_label = StringParam(
        "",
        placeholder="(column name)",
        description=(
            "Override label for the Y axis. Empty falls back to the "
            "column name of the y input's first column."
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
        # Explicit annotations so pyright sees the descriptor-backed attrs.
        self._x_label: str
        self._y_label: str
        self._width: int
        self._height: int
        self._color_by_time: bool
        self._equal_aspect: bool
        self._show_polarization: bool
        self._title: str
        self._add_input(InputPort(_X_INPUT, {IoDataType.DATASET}, optional=False))
        self._add_input(InputPort(_Y_INPUT, {IoDataType.DATASET}, optional=False))
        self._add_output(OutputPort("image", {IoDataType.IMAGE}))
        self._apply_default_params()

    @override
    def process_impl(self) -> None:
        x_df: pd.DataFrame = self.inputs[0].data.payload
        y_df: pd.DataFrame = self.inputs[1].data.payload
        if len(x_df.columns) == 0 or len(y_df.columns) == 0:
            raise KeyError("Hodogram inputs must each have ≥ 1 column")

        x_col = str(x_df.columns[0])
        y_col = str(y_df.columns[0])

        motion = ParticleMotion(x_df[x_col].to_numpy(), y_df[y_col].to_numpy())
        renderer = HodogramRenderer()
        bgr = renderer.render(
            motion,
            x_label=self._x_label or self._axis_label(x_df, x_col),
            y_label=self._y_label or self._axis_label(y_df, y_col),
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

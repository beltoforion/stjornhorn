from __future__ import annotations

# Switch matplotlib to the off-screen Agg backend BEFORE pyplot is
# imported anywhere — keeps figure rendering self-contained and
# prevents matplotlib from claiming the host editor's Qt backend.
import matplotlib

matplotlib.use("Agg")

from enum import IntEnum

import cv2
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase
from core.params import EnumParam, IntParam, StringParam
from core.port import InputPort, OutputPort
from nodes.filters.directional_projection import ATTR_THETAS_RAD

#: Render DPI, matched to PlotXY / PlotSeries so multi-panel mosaics
#: don't pick up scaling discontinuities between plot types.
_RENDER_DPI: int = 100


class Colormap(IntEnum):
    """Matplotlib colormap selection for :class:`PolarHeatmap`."""
    VIRIDIS = 0
    PLASMA  = 1
    INFERNO = 2
    MAGMA   = 3
    TURBO   = 4
    JET     = 5
    HOT     = 6


_CMAP_NAME: dict[Colormap, str] = {
    Colormap.VIRIDIS: "viridis",
    Colormap.PLASMA:  "plasma",
    Colormap.INFERNO: "inferno",
    Colormap.MAGMA:   "magma",
    Colormap.TURBO:   "turbo",
    Colormap.JET:     "jet",
    Colormap.HOT:     "hot",
}


class ThetaZero(IntEnum):
    """Where ``θ = 0`` points on the polar axes."""
    EAST  = 0
    NORTH = 1
    WEST  = 2
    SOUTH = 3


_THETA_ZERO_LOC: dict[ThetaZero, str] = {
    ThetaZero.EAST:  "E",
    ThetaZero.NORTH: "N",
    ThetaZero.WEST:  "W",
    ThetaZero.SOUTH: "S",
}


class ThetaDirection(IntEnum):
    """Whether θ increases CCW (math convention) or CW (geographic)."""
    COUNTERCLOCKWISE = 0
    CLOCKWISE        = 1


class PolarHeatmap(NodeBase):
    """Render a :data:`IoDataType.DATASET` as a polar (θ, r) heatmap.

    Each input column is one azimuth bin; each row is one radial bin.
    Cell ``[r, θ]`` is the column value at row ``r``. Designed for
    directional spectra, antenna patterns, Radon-style sweeps — any
    quantity sampled on a polar (angle, radius) grid.

    Axis binding (in priority order):

    * **Angles**: read from ``df.attrs[ATTR_THETAS_RAD]`` when present
      (set by :class:`DirectionalProjection`); otherwise parsed from
      column names of the form ``"5.0°"``. A row that the parser can't
      decode raises :class:`ValueError` so the failure is loud, not a
      silent mis-axis.
    * **Radius**: ``df.index`` is used verbatim. Index name (e.g.
      ``"frequency_hz"`` from :class:`Spectrum`) becomes the colorbar /
      radial-axis label; an unnamed index falls back to ``"radius"``.

    The pair ``DirectionalProjection → Spectrum → PolarHeatmap``
    reproduces the directional FFT polar plot that the original
    monolithic ``PolarSpectrum`` node provided, while leaving each
    stage usable on its own.
    """

    colormap = EnumParam(
        Colormap,
        Colormap.VIRIDIS,
        constant=True,
        description="Heatmap palette.",
    )
    theta_zero = EnumParam(
        ThetaZero,
        ThetaZero.NORTH,
        constant=True,
        description=(
            "Where ``θ = 0`` points on the polar axes. NORTH matches "
            "the seismic / geographic convention; EAST matches the "
            "mathematical convention."
        ),
    )
    theta_direction = EnumParam(
        ThetaDirection,
        ThetaDirection.CLOCKWISE,
        constant=True,
        description=(
            "Direction of increasing θ. CLOCKWISE matches geographic "
            "azimuths; COUNTERCLOCKWISE matches the math convention."
        ),
    )
    width = IntParam(
        640,
        min=64,
        unit="px",
        constant=True,
        description="Output image width in pixels.",
    )
    height = IntParam(
        640,
        min=64,
        unit="px",
        constant=True,
        description="Output image height in pixels.",
    )
    title = StringParam(
        "",
        placeholder="(no title)",
        constant=True,
        description="Optional plot title rendered above the polar axes.",
    )
    colorbar_label = StringParam(
        "",
        placeholder="(auto)",
        constant=True,
        description=(
            "Override the colorbar label. Empty falls back to "
            "``df.attrs['units']`` of the first column, or a bare "
            "``'amplitude'`` when no unit is known."
        ),
    )

    HEADER_ICON = "scatter_plot"

    def __init__(self) -> None:
        super().__init__("Polar Heatmap", section="Visualization")
        self._colormap:        Colormap
        self._theta_zero:      ThetaZero
        self._theta_direction: ThetaDirection
        self._width:           int
        self._height:          int
        self._title:           str
        self._colorbar_label:  str
        self._add_input(InputPort("dataset", {IoDataType.DATASET}))
        self._add_output(OutputPort("image", {IoDataType.IMAGE}))
        self._apply_default_params()

    @override
    def process_impl(self) -> None:
        in_data = self.inputs[0].data
        df: pd.DataFrame = in_data.payload
        if len(df.columns) < 2 or len(df) < 1:
            self.outputs[0].send(
                IoData.from_image(self._blank_image(), meta=in_data.meta),
            )
            return

        thetas = self._resolve_thetas(df)
        radii = df.index.to_numpy(dtype=np.float64)
        # Sort by angle so the polar mesh wraps cleanly without
        # requiring DirectionalProjection's ordering downstream.
        order = np.argsort(thetas)
        thetas_sorted = thetas[order]
        values = df.to_numpy(dtype=np.float64)[:, order]

        bgr = self._render(
            thetas_sorted,
            radii,
            values,
            cmap_name=_CMAP_NAME[self._colormap],
            theta_zero=_THETA_ZERO_LOC[self._theta_zero],
            theta_direction=(
                -1 if self._theta_direction is ThetaDirection.CLOCKWISE else 1
            ),
            width=self._width,
            height=self._height,
            title=self._title,
            colorbar_label=self._colorbar_label or self._auto_colorbar_label(df),
            radial_label=self._radial_label(df),
        )
        self.outputs[0].send(IoData.from_image(bgr, meta=in_data.meta))

    # ── Pure helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_thetas(df: pd.DataFrame) -> np.ndarray:
        """Return the per-column angle array (radians).

        Prefers ``df.attrs[ATTR_THETAS_RAD]``; falls back to parsing
        column names of the form ``"<deg>°"`` /
        ``"<deg>deg"``.
        """
        thetas = df.attrs.get(ATTR_THETAS_RAD)
        if thetas is not None:
            arr = np.asarray(thetas, dtype=np.float64)
            if arr.shape != (len(df.columns),):
                raise ValueError(
                    f"df.attrs[{ATTR_THETAS_RAD!r}] has shape {arr.shape}, "
                    f"expected ({len(df.columns)},) — one angle per column.",
                )
            return arr
        return np.array(
            [PolarHeatmap._parse_angle_column(str(c)) for c in df.columns],
            dtype=np.float64,
        )

    @staticmethod
    def _parse_angle_column(name: str) -> float:
        """Parse an angle in degrees from a column name like ``"5.0°"``.

        Accepts a trailing ``°`` or ``deg`` suffix (case-insensitive).
        Raises :class:`ValueError` so a misnamed column is loud rather
        than silently mis-binned.
        """
        stripped = name.strip().rstrip("°").strip()
        if stripped.lower().endswith("deg"):
            stripped = stripped[:-3].strip()
        try:
            return float(np.radians(float(stripped)))
        except ValueError as e:
            raise ValueError(
                f"PolarHeatmap could not parse an angle from column "
                f"name {name!r}; expected a numeric value with optional "
                f"'°' or 'deg' suffix, or supply df.attrs"
                f"[{ATTR_THETAS_RAD!r}].",
            ) from e

    @staticmethod
    def _radial_label(df: pd.DataFrame) -> str:
        """Friendly radial-axis label, derived from the index name."""
        if df.index.name:
            return str(df.index.name)
        return "radius"

    @staticmethod
    def _auto_colorbar_label(df: pd.DataFrame) -> str:
        units = df.attrs.get("units")
        if isinstance(units, dict) and len(df.columns) > 0:
            unit = units.get(str(df.columns[0]))
            if unit:
                return str(unit)
        return "amplitude"

    def _blank_image(self) -> np.ndarray:
        """White canvas matching the configured dimensions, used when
        the input is too small to render a meaningful heatmap."""
        return np.full((self._height, self._width, 3), 255, dtype=np.uint8)

    # ── Rendering (off-screen) ────────────────────────────────────────────────

    @staticmethod
    def _render(
        thetas: np.ndarray,
        radii:  np.ndarray,
        values: np.ndarray,
        *,
        cmap_name:       str,
        theta_zero:      str,
        theta_direction: int,
        width:           int,
        height:          int,
        title:           str,
        colorbar_label:  str,
        radial_label:    str,
    ) -> np.ndarray:
        """Render a polar heatmap to a BGR ``uint8`` array.

        ``values`` shape ``(n_radii, n_angles)``. Closes the figure in
        the ``finally`` block so a long-running flow doesn't leak
        figures across frames (parity with the rest of the
        matplotlib-based viz nodes).
        """
        fig = plt.figure(
            figsize=(width / _RENDER_DPI, height / _RENDER_DPI),
            dpi=_RENDER_DPI,
        )
        try:
            ax = fig.add_subplot(111, projection="polar")
            # Wrap angles + values so the polar plot closes back to 2π
            # without a visible seam at the first angle.
            theta_closed = np.concatenate(
                [thetas, [thetas[0] + 2.0 * np.pi]],
            )
            values_closed = np.hstack([values, values[:, :1]])
            T, R = np.meshgrid(theta_closed, radii, indexing="xy")
            mesh = ax.pcolormesh(T, R, values_closed, cmap=cmap_name, shading="auto")
            ax.set_theta_zero_location(theta_zero)
            ax.set_theta_direction(theta_direction)
            ax.set_ylabel(radial_label, labelpad=20)
            if title:
                ax.set_title(title)
            cbar = fig.colorbar(mesh, ax=ax, pad=0.1, shrink=0.8)
            cbar.set_label(colorbar_label)
            fig.tight_layout(pad=0.4)
            fig.canvas.draw()
            rgba = np.asarray(fig.canvas.buffer_rgba())
            return cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGR)
        finally:
            plt.close(fig)

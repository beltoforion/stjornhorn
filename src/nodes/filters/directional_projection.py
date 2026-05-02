from __future__ import annotations

import numpy as np
import pandas as pd
from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase
from core.params import IntParam, StringParam
from core.port import InputPort, OutputPort

#: Key under which :class:`DirectionalProjection` stamps the per-column
#: azimuth angles (radians) onto ``df.attrs``. Downstream visualisers
#: like :class:`PolarHeatmap` read this to bind each column to its
#: angle on the polar axis.
ATTR_THETAS_RAD: str = "thetas_rad"


class DirectionalProjection(NodeBase):
    """Project a 2-component vector signal onto ``n_angles`` directions.

    For each azimuth ``θ_j = j · 2π / n_angles`` (``j = 0 … n_angles-1``)
    emit a column ``r_j(t) = x·cos θ_j + y·sin θ_j``. The result is one
    rotated scalar trace per direction — the building block for
    directional analyses (polar spectra, polarisation sweeps, beam
    forming on two-channel data).

    Conventions:

    * ``θ = 0`` points along ``+x``; θ increases CCW from there in
      mathematical convention. Visualisation nodes downstream are free
      to remap (e.g. polar plot with θ=0 at North, increasing CW).
    * Output columns are named ``"<deg>°"`` (one decimal, e.g.
      ``"5.0°"``) so a stand-alone :class:`PlotSeries` of the output
      reads naturally. The exact angles in radians are also stamped on
      ``df.attrs[ATTR_THETAS_RAD]`` for machine consumers.
    * ``df.attrs`` from the input is forwarded so ``sample_rate`` /
      ``units`` survive the projection. The per-column ``units`` dict
      is rebuilt to point every projected column at the input's
      ``x_column`` unit (``x`` and ``y`` are assumed to share units —
      they are two components of one vector quantity).
    """

    x_column = StringParam(
        "",
        placeholder="(first column)",
        description=(
            "Column name for the first component (x). Empty → first "
            "column of the input dataset."
        ),
    )
    y_column = StringParam(
        "",
        placeholder="(second column)",
        description=(
            "Column name for the second component (y). Empty → second "
            "column of the input dataset."
        ),
    )
    n_angles = IntParam(
        72,
        min=2,
        constant=True,
        description=(
            "Number of azimuth directions to project onto. 72 = 5° "
            "steps; 360 = 1° steps. Cost scales linearly per frame."
        ),
    )

    HEADER_ICON = "arrow_outward"

    def __init__(self) -> None:
        super().__init__("Directional Projection", section="Data")
        self._x_column: str
        self._y_column: str
        self._n_angles: int
        self._add_input(InputPort("dataset", {IoDataType.DATASET}))
        self._add_output(OutputPort("dataset", {IoDataType.DATASET}))
        self._apply_default_params()

    @override
    def process_impl(self) -> None:
        in_io = self.inputs[0].data
        df: pd.DataFrame = in_io.payload
        x_col = self._resolve_column(df, self._x_column, default_index=0)
        y_col = self._resolve_column(df, self._y_column, default_index=1)
        x = df[x_col].to_numpy(dtype=np.float64)
        y = df[y_col].to_numpy(dtype=np.float64)
        n = min(len(x), len(y))
        x = x[:n]
        y = y[:n]

        thetas, projections = self._project(x, y, self._n_angles)
        column_names = [self._format_angle(t) for t in thetas]
        out_df = pd.DataFrame(
            {name: projections[i] for i, name in enumerate(column_names)},
        )
        out_df.attrs = dict(df.attrs)
        out_df.attrs[ATTR_THETAS_RAD] = thetas
        self._propagate_units(out_df, df, x_col, column_names)
        self.outputs[0].send(in_io.clone(payload=out_df))

    # ── Pure helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_column(
        df: pd.DataFrame, requested: str, *, default_index: int,
    ) -> str:
        """Return the column name to use, raising on miss.

        Empty ``requested`` falls back to ``default_index``; a typo
        raises :class:`KeyError` with the available columns listed.
        """
        if requested:
            if requested not in df.columns:
                raise KeyError(
                    f"Column {requested!r} not in dataset; "
                    f"available: {list(df.columns)}",
                )
            return requested
        if default_index >= len(df.columns):
            raise KeyError(
                f"Dataset has only {len(df.columns)} column(s); need at "
                f"least {default_index + 1} for a directional projection.",
            )
        return str(df.columns[default_index])

    @staticmethod
    def _project(
        x: np.ndarray, y: np.ndarray, n_angles: int,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Return ``(thetas, projections)`` for the rotated stack.

        ``thetas`` shape ``(n_angles,)`` (radians, from 0 inclusive to
        2π exclusive); ``projections`` shape ``(n_angles, n_samples)``
        with row ``j`` carrying ``x·cos θ_j + y·sin θ_j``.
        """
        thetas = np.linspace(0.0, 2.0 * np.pi, n_angles, endpoint=False)
        cos_t = np.cos(thetas)[:, None]
        sin_t = np.sin(thetas)[:, None]
        projections = cos_t * x + sin_t * y
        return thetas, projections

    @staticmethod
    def _format_angle(theta_rad: float) -> str:
        """Format an angle in radians as a degree-suffixed column name."""
        return f"{np.degrees(theta_rad):.1f}°"

    @staticmethod
    def _propagate_units(
        out_df: pd.DataFrame,
        in_df: pd.DataFrame,
        source_column: str,
        new_columns: list[str],
    ) -> None:
        """Carry ``df.attrs['units']`` forward, mapping every projected
        column at the input ``source_column``'s unit (the two source
        components are assumed to share units — they are two
        components of the same vector quantity)."""
        units = in_df.attrs.get("units")
        if not isinstance(units, dict):
            return
        unit = units.get(source_column)
        if unit is None:
            return
        out_df.attrs["units"] = {col: unit for col in new_columns}

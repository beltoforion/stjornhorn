from __future__ import annotations

# Switch matplotlib to the off-screen Agg backend BEFORE pyplot is
# imported anywhere in the module — this keeps figure rendering
# self-contained and prevents matplotlib from claiming the default
# Qt/Tk backend that the host editor already runs.
import matplotlib

matplotlib.use("Agg")

import cv2
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase
from core.params import BoolParam, IntParam, StringParam
from core.port import InputPort, OutputPort

#: Render DPI used when sizing the matplotlib figure. Width / height in
#: pixels are converted to inches via ``size_px / _RENDER_DPI`` because
#: matplotlib expects inches; 100 keeps the math simple and produces
#: text-readable plots at typical pixel sizes.
_RENDER_DPI: int = 100


class PlotXY(NodeBase):
    """Render two columns of a :data:`IoDataType.DATASET` as an XY line plot.

    Output is a BGR image so it slots into the viewer / file-sink
    pipeline. A one-column input is rejected — insert
    :class:`AddIndexColumn` upstream to add an explicit X axis. Axis
    labels come from the column names; ``df.attrs["units"]`` is
    appended as ``"col [unit]"`` when set.
    """

    x_column = StringParam(
        "",
        placeholder="(first column)",
        description=(
            "Column name for the X axis. Leave empty to use the first "
            "column of the input dataset."
        ),
    )
    y_column = StringParam(
        "",
        placeholder="(second column)",
        description=(
            "Column name for the Y axis. Leave empty to use the second "
            "column of the input dataset."
        ),
    )
    width = IntParam(
        640,
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
    title = StringParam(
        "",
        placeholder="(no title)",
        description="Optional plot title rendered above the axes.",
    )
    grid = BoolParam(
        True,
        description="Draw a faint grid across the plot area.",
    )

    def __init__(self) -> None:
        super().__init__("Plot XY", section="Visualization")
        self._add_input(InputPort("dataset", {IoDataType.DATASET}))
        # Optional band overlay: when both endpoints are connected, the
        # renderer paints a translucent vertical band across that x-range.
        # Either one missing → no band (current behaviour).
        self._add_input(InputPort("band_start", {IoDataType.SCALAR}, optional=True))
        self._add_input(InputPort("band_end",   {IoDataType.SCALAR}, optional=True))
        self._add_output(OutputPort("image", {IoDataType.IMAGE}))
        self._apply_default_params()

    @override
    def process_impl(self) -> None:
        df: pd.DataFrame = self.inputs[0].data.payload
        x_col = self._resolve_column(df, self._x_column, default_index=0)
        y_col = self._resolve_column(df, self._y_column, default_index=1)

        band = self._resolve_band()

        bgr = self._render(
            df[x_col].to_numpy(),
            df[y_col].to_numpy(),
            x_label=self._axis_label(df, x_col),
            y_label=self._axis_label(df, y_col),
            width=self._width,
            height=self._height,
            title=self._title,
            grid=self._grid,
            band=band,
        )
        self.outputs[0].send(IoData.from_image(bgr))

    # ── Pure helpers (testable without rendering) ─────────────────────────────

    def _resolve_band(self) -> tuple[float, float] | None:
        """Return ``(start, end)`` if both band ports carry SCALARs, else ``None``.

        Order is normalised so a reversed pair still draws a forward band —
        matplotlib's ``axvspan`` accepts either, but normalising up-front
        keeps downstream consumers (snapshots, regression baselines)
        deterministic.
        """
        bs_port = self.inputs[1]
        be_port = self.inputs[2]
        if not (bs_port.has_data and be_port.has_data):
            return None
        bs = float(bs_port.data.payload)
        be = float(be_port.data.payload)
        if bs > be:
            bs, be = be, bs
        return (bs, be)

    @staticmethod
    def _resolve_column(
        df: pd.DataFrame, requested: str, *, default_index: int
    ) -> str:
        """Return the column name to plot, raising on miss.

        An empty ``requested`` falls back to the column at
        ``default_index`` so a freshly-dropped node renders without
        the user having to type column names. A non-empty miss raises
        :class:`KeyError` with the available columns listed; an empty
        request with too few columns points the user at
        :class:`~nodes.filters.add_index_column.AddIndexColumn`, which
        is the supported way to add a synthetic X axis.
        """
        if requested:
            if requested not in df.columns:
                raise KeyError(
                    f"Column {requested!r} not in dataset; "
                    f"available: {list(df.columns)}"
                )
            return requested
        if default_index >= len(df.columns):
            raise KeyError(
                f"Dataset has only {len(df.columns)} column(s); "
                f"need at least {default_index + 1} to plot. "
                f"Insert an AddIndexColumn node upstream to add an X axis."
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

    # ── Rendering (off-screen) ────────────────────────────────────────────────

    @staticmethod
    def _render(
        x: np.ndarray,
        y: np.ndarray,
        *,
        x_label: str,
        y_label: str,
        width: int,
        height: int,
        title: str,
        grid: bool,
        band: tuple[float, float] | None = None,
    ) -> np.ndarray:
        """Render the plot to a BGR ``uint8`` array via matplotlib Agg.

        ``band`` paints a translucent vertical span (``axvspan``) behind
        the trace — typically used to highlight the slice the rest of
        the flow is currently focused on. Painted *before* the line so
        the trace stays legible.

        Always closes the figure before returning so a long-running
        flow doesn't leak figures across frames.
        """
        fig = plt.figure(
            figsize=(width / _RENDER_DPI, height / _RENDER_DPI),
            dpi=_RENDER_DPI,
        )
        try:
            ax = fig.add_subplot(111)
            if band is not None:
                ax.axvspan(band[0], band[1], alpha=0.20, color="#ffd24a", zorder=0)
            ax.plot(x, y)
            ax.set_xlabel(x_label)
            ax.set_ylabel(y_label)
            if title:
                ax.set_title(title)
            if grid:
                ax.grid(True, alpha=0.3)
            fig.tight_layout(pad=0.4)
            fig.canvas.draw()
            rgba = np.asarray(fig.canvas.buffer_rgba())
            return cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGR)
        finally:
            plt.close(fig)

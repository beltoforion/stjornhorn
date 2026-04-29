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

    Generic enough to cover waveforms (time vs amplitude), CV curves
    (voltage vs capacitance), diode I-V characteristics, spectra, and
    any other "Y vs X" view from a single ``Dataset`` payload — that
    breadth is the whole point of project Datenkrake's single
    ``DATASET`` payload kind.

    Output is a 3-channel BGR image so it slots into the existing
    viewer / file-sink pipeline without a special path. Matplotlib's
    off-screen ``Agg`` backend is used for rendering; no GUI thread
    is touched.

    The node always plots two named columns. A one-column input is
    rejected with a clear error; insert
    :class:`~nodes.filters.add_index_column.AddIndexColumn` upstream
    to add an explicit X axis (sample number, or time in seconds via
    ``step = 1 / sample_rate``).

    Axis labels come from the column names. If ``df.attrs["units"]``
    is set (a ``{column: unit_string}`` dict, populated by upstream
    nodes like ``SetUnits`` or by a domain-aware source), the unit is
    appended to each label as ``"col [unit]"``.

    Parameters:
      x_column -- column name for the X axis. Empty (default) picks the
                  first column of the input dataset.
      y_column -- column name for Y. Empty (default) picks the second
                  column.
      width    -- output image width in pixels (≥ 64).
      height   -- output image height in pixels (≥ 64).
      title    -- overlay title; empty (default) shows none.
      grid     -- when True (default), draws a faint grid.
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
        self._add_output(OutputPort("image", {IoDataType.IMAGE}))
        self._apply_default_params()

    @override
    def process_impl(self) -> None:
        df: pd.DataFrame = self.inputs[0].data.payload
        x_col = self._resolve_column(df, self._x_column, default_index=0)
        y_col = self._resolve_column(df, self._y_column, default_index=1)

        bgr = self._render(
            df[x_col].to_numpy(),
            df[y_col].to_numpy(),
            x_label=self._axis_label(df, x_col),
            y_label=self._axis_label(df, y_col),
            width=self._width,
            height=self._height,
            title=self._title,
            grid=self._grid,
        )
        self.outputs[0].send(IoData.from_image(bgr))

    # ── Pure helpers (testable without rendering) ─────────────────────────────

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
    ) -> np.ndarray:
        """Render the plot to a BGR ``uint8`` array via matplotlib Agg.

        Always closes the figure before returning so a long-running
        flow doesn't leak figures across frames.
        """
        fig = plt.figure(
            figsize=(width / _RENDER_DPI, height / _RENDER_DPI),
            dpi=_RENDER_DPI,
        )
        try:
            ax = fig.add_subplot(111)
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

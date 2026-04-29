from __future__ import annotations

from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase
from core.params import BoolParam, FloatParam, IntParam, StringParam
from core.port import InputPort, OutputPort
from nodes.filters.add_index_column import AddIndexColumn
from nodes.filters.plot_xy import PlotXY

#: Internal column name used for the synthetic time axis. Hidden from
#: the user — PlotSeries always addresses it by this fixed name.
_TIME_COL: str = "t"


class PlotSeries(NodeBase):
    """Synthesise a time axis and render a single-column trace as an XY plot.

    Combines :class:`~nodes.filters.add_index_column.AddIndexColumn` and
    :class:`~nodes.filters.plot_xy.PlotXY` into one node for the common
    case of plotting a raw single-column :data:`IoDataType.DATASET`
    (e.g. directly from :class:`~nodes.sources.csv_source.CsvSource`).

    Internally the two nodes are instantiated as private members and
    driven in sequence during :meth:`process_impl` — no logic is
    duplicated.

    Parameters:
      step     -- time step between samples (seconds). Use
                  ``1 / sample_rate``: e.g. ``0.125`` for 8 Hz.
      start    -- time of the first sample (default ``0.0``).
      y_column -- column to plot on Y. Empty (default) picks the first
                  column of the input dataset (typically ``c0`` from
                  :class:`~nodes.sources.csv_source.CsvSource`).
      width / height -- output image size in pixels (≥ 64).
      title    -- optional plot title.
      grid     -- draw a faint grid (default True).
    """

    step = FloatParam(
        1.0,
        min=0.0,
        min_exclusive=True,
        description=(
            "Time step between samples in seconds. "
            "Use 1 / sample_rate, e.g. 0.125 for 8 Hz data."
        ),
    )
    start = FloatParam(
        0.0,
        description="Time of the first sample.",
    )
    y_column = StringParam(
        "",
        placeholder="(first column)",
        description=(
            "Column name for the Y axis. Leave empty to use the first "
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
        super().__init__("Plot Series", section="Visualization")
        # Explicit annotations so pyright sees the descriptor-backed attrs.
        self._step: float
        self._start: float
        self._y_column: str
        self._width: int
        self._height: int
        self._title: str
        self._grid: bool
        self._add_input(InputPort("dataset", {IoDataType.DATASET}))
        self._add_output(OutputPort("image", {IoDataType.IMAGE}))
        self._apply_default_params()

        self._indexer = AddIndexColumn()
        self._plotter = PlotXY()

    @override
    def process_impl(self) -> None:
        # ── Step 1: add synthetic time axis ──────────────────────────────
        self._indexer.name = _TIME_COL
        self._indexer.start = self._start
        self._indexer.step = self._step
        self._indexer.inputs[0].receive(self.inputs[0].data)

        indexed = self._indexer.outputs[0].last_emitted
        if indexed is None:
            return

        # ── Step 2: render the XY plot ───────────────────────────────────
        self._plotter.x_column = _TIME_COL
        self._plotter.y_column = self._y_column
        self._plotter.width = self._width
        self._plotter.height = self._height
        self._plotter.title = self._title
        self._plotter.grid = self._grid
        self._plotter.inputs[0].receive(indexed)

        result = self._plotter.outputs[0].last_emitted
        if result is None:
            return

        self.outputs[0].send(result)

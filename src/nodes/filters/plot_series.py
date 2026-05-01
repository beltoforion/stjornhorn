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

    Combines :class:`AddIndexColumn` + :class:`PlotXY` into one node
    for plotting a raw single-column :data:`IoDataType.DATASET`. Set
    ``step = 1 / sample_rate`` for a seconds axis.
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
        # Band overlay endpoints, expressed in sample-row coordinates so
        # the upstream :class:`SlidingWindow` can wire its ``window_start``
        # / ``window_end`` SCALAR outputs straight in. PlotSeries converts
        # those row indices to the time axis (``start + idx * step``)
        # before the renderer sees them — keeps the band aligned with the
        # synthesized x-axis without the flow author doing the math.
        self._add_input(InputPort("band_start", {IoDataType.SCALAR}, optional=True))
        self._add_input(InputPort("band_end",   {IoDataType.SCALAR}, optional=True))
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
        # Forward band endpoints to PlotXY in time coordinates. Always
        # push fresh values — the inner PlotXY's optional band ports
        # don't gate dispatch, but stale values from a previous frame
        # would survive across runs without an explicit overwrite.
        bs_port = self.inputs[1]
        be_port = self.inputs[2]
        if bs_port.has_data and be_port.has_data:
            bs_time = self._start + float(bs_port.data.payload) * self._step
            be_time = self._start + float(be_port.data.payload) * self._step
            self._plotter.inputs[1].receive(IoData.from_scalar(bs_time))
            self._plotter.inputs[2].receive(IoData.from_scalar(be_time))
        else:
            # Clear so a partially-connected band on a previous frame
            # doesn't leak into the next render.
            self._plotter.inputs[1].clear()
            self._plotter.inputs[2].clear()
        self._plotter.inputs[0].receive(indexed)

        result = self._plotter.outputs[0].last_emitted
        if result is None:
            return

        self.outputs[0].send(result)

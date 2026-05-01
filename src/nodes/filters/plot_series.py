from __future__ import annotations

import cv2
import numpy as np
from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase
from core.params import BoolParam, FloatParam, IntParam, StringParam
from core.port import InputPort, OutputPort
from nodes.filters.add_index_column import AddIndexColumn
from nodes.filters.plot_xy import AxesDescriptor, PlotXY

#: Internal column name used for the synthetic time axis. Hidden from
#: the user — PlotSeries always addresses it by this fixed name.
_TIME_COL: str = "t"

#: Band overlay colour (BGR) and alpha, matched to PlotXY's ``axvspan``
#: defaults so the cv2-overlay path produces a visually-equivalent band.
_BAND_BGR:   tuple[int, int, int] = (74, 210, 255)  # #ffd24a in RGB → BGR
_BAND_ALPHA: float = 0.20


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
        # Cached trace render so a moving band (driven by SlidingWindow
        # in the animated-hodogram demo) doesn't force matplotlib to
        # re-render the full waveform every tick. Keyed on
        # ``(id(input_iodata), step, start, y_column, width, height,
        # title, grid)`` — IoData is treated as immutable by framework
        # convention (``OutputPort.send`` clones on every emit), so a
        # different identity always means different content. Any
        # upstream filter that emits a fresh DataFrame per tick (shift,
        # resample) naturally invalidates the cache; a held one-shot
        # input keeps the cache warm across the streaming clock.
        self._cache_key:    tuple | None              = None
        self._cache_base:   np.ndarray | None         = None
        self._cache_axes:   AxesDescriptor | None     = None

    @override
    def process_impl(self) -> None:
        in_io = self.inputs[0].data
        cache_key = (
            id(in_io), self._step, self._start, self._y_column,
            self._width, self._height, self._title, self._grid,
        )
        if (
            cache_key != self._cache_key
            or self._cache_base is None
            or self._cache_axes is None
        ):
            self._refresh_cache(in_io, cache_key)

        # Cv2 overlay against the cached base. Each tick that arrives
        # with both band ports fresh paints a fresh rectangle; a tick
        # without band data emits the unmodified base.
        bs_port = self.inputs[1]
        be_port = self.inputs[2]
        if bs_port.has_data and be_port.has_data:
            bs_time = self._start + float(bs_port.data.payload) * self._step
            be_time = self._start + float(be_port.data.payload) * self._step
            assert self._cache_base is not None and self._cache_axes is not None
            result = self._overlay_band(
                self._cache_base, self._cache_axes, bs_time, be_time,
            )
        else:
            assert self._cache_base is not None
            result = self._cache_base.copy()

        self.outputs[0].send(IoData.from_image(result))

    # ── Internals ──────────────────────────────────────────────────────────────

    def _refresh_cache(self, in_io: IoData, cache_key: tuple) -> None:
        """Run AddIndexColumn + matplotlib once and stash the bitmap +
        axes geometry. Subsequent ticks with the same dataset identity
        reuse this cache and only repaint the band in cv2.
        """
        self._indexer.name = _TIME_COL
        self._indexer.start = self._start
        self._indexer.step = self._step
        self._indexer.inputs[0].receive(in_io)
        indexed = self._indexer.outputs[0].last_emitted
        if indexed is None:
            return
        df = indexed.payload
        x_arr = df[_TIME_COL].to_numpy()
        y_col = self._plotter._resolve_column(df, self._y_column, default_index=1)
        y_arr = df[y_col].to_numpy()

        base, axes = PlotXY.render_with_axes(
            x_arr, y_arr,
            x_label=self._plotter._axis_label(df, _TIME_COL),
            y_label=self._plotter._axis_label(df, y_col),
            width=self._width, height=self._height,
            title=self._title, grid=self._grid,
            band=None,  # band painted in cv2 below for fast per-frame redraw
        )
        self._cache_key  = cache_key
        self._cache_base = base
        self._cache_axes = axes

    @staticmethod
    def _overlay_band(
        base: np.ndarray, axes: AxesDescriptor, bs_time: float, be_time: float,
    ) -> np.ndarray:
        """Paint a translucent yellow rectangle over the band's x-range
        of the cached bitmap. Reverses endpoints so a wired-backwards
        band still draws as a forward span (parity with matplotlib's
        ``axvspan`` and the existing ``_resolve_band`` normalisation)."""
        if bs_time > be_time:
            bs_time, be_time = be_time, bs_time
        ax_x0,    ax_x1    = axes.pixel_x
        data_x0,  data_x1  = axes.data_xlim
        if data_x1 == data_x0:
            return base.copy()
        scale = (ax_x1 - ax_x0) / (data_x1 - data_x0)
        bs_px = ax_x0 + (bs_time - data_x0) * scale
        be_px = ax_x0 + (be_time - data_x0) * scale
        # Clip so a band partially-off-screen still draws the visible
        # portion rather than spilling onto the axes labels.
        left  = int(round(max(ax_x0, min(ax_x1, bs_px))))
        right = int(round(max(ax_x0, min(ax_x1, be_px))))
        out = base.copy()
        if right <= left:
            return out
        # matplotlib y is bottom-up; image y is top-down. axes.pixel_y
        # is (bottom_y, top_y) in matplotlib coords; flip via
        # ``canvas_height - y``.
        ay0, ay1 = axes.pixel_y
        top    = int(round(axes.canvas_height - ay1))
        bottom = int(round(axes.canvas_height - ay0))
        roi = out[top:bottom, left:right]
        if roi.size == 0:
            return out
        overlay = np.full_like(roi, _BAND_BGR, dtype=np.uint8)
        out[top:bottom, left:right] = cv2.addWeighted(
            overlay, _BAND_ALPHA, roi, 1.0 - _BAND_ALPHA, 0,
        )
        return out

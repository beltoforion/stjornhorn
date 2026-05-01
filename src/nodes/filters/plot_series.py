from __future__ import annotations

import cv2
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase
from core.params import BoolParam, FloatParam, IntParam, StringParam
from core.port import InputPort, OutputPort
from nodes.filters.plot_xy import _RENDER_DPI, AxesDescriptor

#: Band overlay colour (BGR) and alpha, matched to PlotXY's ``axvspan``
#: defaults so the cv2-overlay path produces a visually-equivalent band.
_BAND_BGR:   tuple[int, int, int] = (74, 210, 255)  # #ffd24a in RGB → BGR
_BAND_ALPHA: float = 0.20


class PlotSeries(NodeBase):
    """Synthesise a time axis and render every column of the input
    :data:`IoDataType.DATASET` as an independent time-series trace,
    stacked vertically with a shared time axis.

    The input is interpreted as a stack of independent channels — *not*
    as ``y = f(x)`` (the :class:`PlotXY` model). A single-column input
    plots one trace in its own panel; an N-column input from
    :class:`~nodes.filters.join_datasets.JoinDatasets` produces N
    panels (top-to-bottom) sharing the X axis. Each panel's Y label
    is the column name; the time axis is labelled only on the bottom
    panel so the stack stays compact.

    Set ``step = 1 / sample_rate`` for a seconds axis. Optional
    ``y_columns`` filters which columns to plot when the input has
    extra channels you don't want; empty plots every column.

    Band overlay endpoints arrive as ``window_start`` / ``window_end``
    keys on the input's :class:`~core.io_data.IoMeta` (typically
    stamped by :class:`~nodes.filters.sliding_window.SlidingWindow` on
    its passthrough output) and are converted internally to time
    coordinates via ``start`` / ``step``. The band spans every panel
    so the highlighted window lines up across channels.
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
    y_columns = StringParam(
        "",
        placeholder="(all columns)",
        description=(
            "Comma-separated list of column names to plot as overlaid "
            "series. Leave empty to plot every column of the input "
            "dataset (the typical case after a JoinDatasets merge)."
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
        360,
        min=64,
        unit="px",
        constant=True,
        description="Output image height in pixels.",
    )
    title = StringParam(
        "",
        placeholder="(no title)",
        constant=True,
        description="Optional plot title rendered above the axes.",
    )
    grid = BoolParam(
        True,
        constant=True,
        description="Draw a faint grid across the plot area.",
    )

    def __init__(self) -> None:
        super().__init__("Plot Series", section="Visualization")
        # Explicit annotations so pyright sees the descriptor-backed attrs.
        self._step:      float
        self._start:     float
        self._y_columns: str
        self._width:     int
        self._height:    int
        self._title:     str
        self._grid:      bool
        self._add_input(InputPort("dataset", {IoDataType.DATASET}))
        self._add_output(OutputPort("image", {IoDataType.IMAGE}))
        self._apply_default_params()

        # Cached trace render so a moving band (driven by SlidingWindow
        # in the animated-hodogram demo) doesn't force matplotlib to
        # re-render the full waveform every tick. Keyed on the input
        # *DataFrame* identity (preserved across SlidingWindow's
        # passthrough re-emits — each tick wraps the same DataFrame in
        # a fresh IoData) plus the visual params + selected columns.
        # Any upstream that emits a different DataFrame per tick
        # (shift, resample) gets a different ``id(payload)`` and
        # re-renders correctly.
        #
        # ``_cache_df`` keeps a reference to the cached DataFrame so its
        # ``id()`` stays unique while the cache is live. Without it,
        # CPython would happily recycle the memory of a GC'd DataFrame
        # for the *next* emit's DataFrame, faking a cache hit on
        # genuinely-different content.
        self._cache_key:    tuple | None              = None
        self._cache_base:   np.ndarray | None         = None
        self._cache_axes:   AxesDescriptor | None     = None
        self._cache_df:     pd.DataFrame | None       = None

    @override
    def process_impl(self) -> None:
        in_io = self.inputs[0].data
        df: pd.DataFrame = in_io.payload
        columns = self._select_columns(df)
        cache_key = (
            id(in_io.payload), self._step, self._start, tuple(columns),
            self._width, self._height, self._title, self._grid,
        )
        if (
            cache_key != self._cache_key
            or self._cache_base is None
            or self._cache_axes is None
        ):
            self._refresh_cache(df, columns, cache_key)

        # Read band endpoints from the input's IoMeta. SlidingWindow
        # stamps ``window_start`` / ``window_end`` (sample-row indices)
        # on every emit; PlotSeries converts to the time axis here so
        # the band aligns with the synthesized x-axis.
        ws = in_io.meta.get("window_start")
        we = in_io.meta.get("window_end")
        if ws is not None and we is not None:
            bs_time = self._start + float(ws) * self._step
            be_time = self._start + float(we) * self._step
            assert self._cache_base is not None and self._cache_axes is not None
            result = self._overlay_band(
                self._cache_base, self._cache_axes, bs_time, be_time,
            )
        else:
            assert self._cache_base is not None
            result = self._cache_base.copy()

        self.outputs[0].send(IoData.from_image(result))

    # ── Internals ──────────────────────────────────────────────────────────────

    def _select_columns(self, df: pd.DataFrame) -> list[str]:
        """Resolve ``y_columns`` against the input.

        Empty → every column of *df* (the JoinDatasets case). Otherwise
        a comma-separated list, validated against the input columns so
        a typo is loud rather than silently dropping a series.
        """
        raw = self._y_columns.strip()
        if not raw:
            return [str(c) for c in df.columns]
        wanted = [c.strip() for c in raw.split(",") if c.strip()]
        for col in wanted:
            if col not in df.columns:
                raise KeyError(
                    f"Column {col!r} not in dataset; "
                    f"available: {list(df.columns)}",
                )
        return wanted

    def _refresh_cache(
        self, df: pd.DataFrame, columns: list[str], cache_key: tuple,
    ) -> None:
        """Render every selected column as an overlaid line on the
        synthetic time axis and stash bitmap + axes geometry. Subsequent
        ticks with the same DataFrame identity reuse this cache and
        only repaint the band in cv2.
        """
        n = len(df)
        x = self._start + np.arange(n, dtype=np.float64) * self._step
        y_series = {col: df[col].to_numpy() for col in columns}

        base, axes = self._render(
            x, y_series,
            x_label=self._x_axis_label(df),
            width=self._width, height=self._height,
            title=self._title, grid=self._grid,
        )
        self._cache_key  = cache_key
        self._cache_base = base
        self._cache_axes = axes
        # Keep a reference so the DataFrame can't be garbage-collected
        # while its id() is the cache key — otherwise Python may recycle
        # its address for the next emit's DataFrame and serve a stale
        # bitmap on what's actually a different input.
        self._cache_df   = df

    @staticmethod
    def _x_axis_label(df: pd.DataFrame) -> str:
        """Time-axis label, optionally annotated with the unit
        ``df.attrs["units"]`` carries for the synthetic time channel
        (e.g. ``"time [s]"``). Falls back to a bare ``"time"`` when no
        unit is attached."""
        units = df.attrs.get("units")
        if isinstance(units, dict):
            unit = units.get("time")
            if unit:
                return f"time [{unit}]"
        return "time"

    @staticmethod
    def _render(
        x: np.ndarray,
        y_series: dict[str, np.ndarray],
        *,
        x_label: str,
        width: int,
        height: int,
        title: str,
        grid: bool,
    ) -> tuple[np.ndarray, AxesDescriptor]:
        """Render every series in *y_series* as its own panel stacked
        top-to-bottom with a shared X (time) axis. Returns the BGR
        bitmap plus an :class:`AxesDescriptor` covering the union of
        every panel's plot area — the band-overlay path uses this to
        paint a single rectangle that spans the whole stack so the
        highlighted window lines up across channels.

        A single-series input collapses to one panel and renders just
        like the legacy single-column behaviour.
        """
        fig, axes = plt.subplots(
            nrows=max(len(y_series), 1),
            ncols=1,
            sharex=True,
            figsize=(width / _RENDER_DPI, height / _RENDER_DPI),
            dpi=_RENDER_DPI,
        )
        try:
            # ``plt.subplots`` returns a single Axes for nrows=1; wrap
            # in a list so the loop below stays uniform across the
            # single- and multi-panel cases.
            ax_list = [axes] if len(y_series) <= 1 else list(axes)
            items = list(y_series.items())
            if not items:
                # Empty selection (no columns chosen and no input
                # columns). Render an empty plot rather than crashing.
                ax_list[0].plot([], [])
            for ax, (label, y) in zip(ax_list, items):
                ax.plot(x, y)
                ax.set_ylabel(label)
                if grid:
                    ax.grid(True, alpha=0.3)
            ax_list[-1].set_xlabel(x_label)
            if title:
                fig.suptitle(title)
            fig.tight_layout(pad=0.4)
            fig.canvas.draw()
            # Band overlay rectangle spans the whole panel tower —
            # union of every panel's pixel-y range, with the gaps
            # between panels included so the highlight reads as one
            # continuous band, not discrete strips.
            pixel_x = tuple(ax_list[0].bbox.intervalx)
            data_xlim = tuple(ax_list[0].get_xlim())
            y_lows  = [a.bbox.y0 for a in ax_list]
            y_highs = [a.bbox.y1 for a in ax_list]
            descriptor = AxesDescriptor(
                pixel_x=pixel_x,
                pixel_y=(min(y_lows), max(y_highs)),
                data_xlim=data_xlim,
                canvas_height=int(height),
            )
            rgba = np.asarray(fig.canvas.buffer_rgba())
            bgr = cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGR)
            return bgr, descriptor
        finally:
            plt.close(fig)

    @staticmethod
    def _overlay_band(
        base: np.ndarray, axes: AxesDescriptor, bs_time: float, be_time: float,
    ) -> np.ndarray:
        """Paint a translucent yellow rectangle over the band's x-range
        of the cached bitmap. Reverses endpoints so a wired-backwards
        band still draws as a forward span (parity with matplotlib's
        ``axvspan``)."""
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

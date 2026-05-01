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
from core.params import BoolParam, EnumParam, FloatParam, IntParam, StringParam
from core.port import InputPort, OutputPort

#: Render DPI, matched to PlotXY / PlotSeries so multi-panel mosaics
#: don't pick up scaling discontinuities between plot types.
_RENDER_DPI: int = 100

#: Tiny floor under the dB conversion so a silent angle/freq cell
#: doesn't blow up to ``-inf``. Scaled relative to the spectrum's
#: peak so the dynamic range stays meaningful regardless of input
#: magnitude.
_DB_FLOOR_REL: float = 1e-6


class Colormap(IntEnum):
    """Matplotlib colormap selection for :class:`PolarSpectrum`."""
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


class PolarSpectrum(NodeBase):
    """Directional / polarisation spectrum of two-component data.

    For each azimuth θ ∈ [0, 2π), rotate the input pair (x, y) into a
    single trace ``r_θ(t) = x cos θ + y sin θ``, take the magnitude
    FFT, and plot the resulting (angle, frequency, amplitude) as a
    polar heatmap. Useful for seeing which directions of motion carry
    which frequency content — particle-motion analytics for
    seismology and similar two-component sensor data.

    Pairs naturally with :class:`SlidingWindow` upstream: each window
    produces one polar-spectrum frame, animating alongside a
    :class:`PlotXY`-rendered hodogram and the source waveforms.

    Convention:

    * ``x_column`` / ``y_column`` default to the first / second
      columns of the input dataset (the typical
      ``JoinDatasets(N, E)`` shape).
    * ``θ = 0`` points up (sets ``set_theta_zero_location("N")``)
      and angles increase clockwise — the geographic / seismic
      convention. Different communities prefer different
      conventions; revisit if a real consumer fights this.
    * ``sample_rate`` is in Hz; ``freq_max = 0`` shows the full
      Nyquist range, otherwise clips the radial axis.
    * ``db_scale = True`` plots ``20 log10(|F|)`` so wide-dynamic-range
      spectra read cleanly; linear is available for cases where the
      raw amplitude matters.
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
    sample_rate = FloatParam(
        8.0,
        min=0.0,
        min_exclusive=True,
        constant=True,
        unit="Hz",
        description=(
            "Sample rate of the input signal, used to label the "
            "frequency axis and set the Nyquist limit."
        ),
    )
    n_angles = IntParam(
        72,
        min=4,
        constant=True,
        description=(
            "Azimuth resolution: number of angles the (x, y) pair is "
            "rotated through. 72 = 5° steps; 360 = 1° steps. Cost "
            "scales linearly per frame."
        ),
    )
    freq_max = FloatParam(
        0.0,
        min=0.0,
        constant=True,
        unit="Hz",
        description=(
            "Upper frequency on the radial axis. ``0`` shows the full "
            "Nyquist range; lower values zoom into the band of interest."
        ),
    )
    db_scale = BoolParam(
        True,
        constant=True,
        description=(
            "When True, plot ``20 log10(|F|)`` for wide-dynamic-range "
            "spectra. Linear amplitude when False."
        ),
    )
    colormap = EnumParam(
        Colormap,
        Colormap.VIRIDIS,
        constant=True,
        description="Heatmap palette.",
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

    def __init__(self) -> None:
        super().__init__("Polar Spectrum", section="Visualization")
        # Explicit annotations so pyright sees the descriptor-backed attrs.
        self._x_column:    str
        self._y_column:    str
        self._sample_rate: float
        self._n_angles:    int
        self._freq_max:    float
        self._db_scale:    bool
        self._colormap:    Colormap
        self._width:       int
        self._height:      int
        self._title:       str
        self._add_input(InputPort("dataset", {IoDataType.DATASET}))
        self._add_output(OutputPort("image", {IoDataType.IMAGE}))
        self._apply_default_params()

    @override
    def process_impl(self) -> None:
        df: pd.DataFrame = self.inputs[0].data.payload
        x_col = self._resolve_column(df, self._x_column, default_index=0)
        y_col = self._resolve_column(df, self._y_column, default_index=1)
        x = df[x_col].to_numpy(dtype=np.float64)
        y = df[y_col].to_numpy(dtype=np.float64)
        n = min(len(x), len(y))
        if n < 4:
            # Too few samples to produce a meaningful FFT — emit a
            # blank canvas of the right dimensions so downstream
            # mosaic / video sinks don't see a frame-shape change.
            self.outputs[0].send(
                IoData.from_image(self._blank_image()),
            )
            return

        thetas, freqs, spec = self._compute_spectrum(
            x[:n], y[:n], self._sample_rate, self._n_angles,
        )
        freq_max = self._freq_max if self._freq_max > 0.0 else float(freqs[-1])
        mask = freqs <= freq_max
        freqs_show = freqs[mask]
        spec_show  = spec[:, mask]
        if self._db_scale:
            spec_show = self._to_db(spec_show)

        bgr = self._render(
            thetas, freqs_show, spec_show,
            db_scale=self._db_scale,
            cmap_name=_CMAP_NAME[self._colormap],
            width=self._width, height=self._height,
            title=self._title,
        )
        self.outputs[0].send(IoData.from_image(bgr))

    # ── Pure helpers (testable without rendering) ─────────────────────────────

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
                f"least {default_index + 1} for a polar spectrum.",
            )
        return str(df.columns[default_index])

    @staticmethod
    def _compute_spectrum(
        x: np.ndarray, y: np.ndarray, sample_rate: float, n_angles: int,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Return ``(thetas, freqs, spec)`` for the rotated FFT stack.

        ``thetas`` shape ``(n_angles,)`` (radians), ``freqs`` shape
        ``(n_freq,)`` (Hz), ``spec`` shape ``(n_angles, n_freq)``
        (linear magnitude). A Hann window is applied per rotation to
        suppress spectral leakage on short windows — the typical
        SlidingWindow consumer.
        """
        n = len(x)
        window = np.hanning(n)
        x_w = x * window
        y_w = y * window
        thetas = np.linspace(0.0, 2.0 * np.pi, n_angles, endpoint=False)
        cos_t = np.cos(thetas)[:, None]
        sin_t = np.sin(thetas)[:, None]
        rotated = cos_t * x_w + sin_t * y_w
        spec = np.abs(np.fft.rfft(rotated, axis=1))
        freqs = np.fft.rfftfreq(n, d=1.0 / sample_rate)
        return thetas, freqs, spec

    @staticmethod
    def _to_db(spec: np.ndarray) -> np.ndarray:
        """Convert a linear-magnitude spectrum to dB with a floor
        scaled relative to the peak so silent cells don't go to
        ``-inf`` while the dynamic range stays meaningful."""
        peak = float(np.max(spec))
        floor = max(peak * _DB_FLOOR_REL, 1e-12)
        return 20.0 * np.log10(np.maximum(spec, floor))

    def _blank_image(self) -> np.ndarray:
        """White canvas matching the configured dimensions, used when
        the input is too short to FFT meaningfully."""
        return np.full((self._height, self._width, 3), 255, dtype=np.uint8)

    # ── Rendering (off-screen) ────────────────────────────────────────────────

    @staticmethod
    def _render(
        thetas: np.ndarray,
        freqs:  np.ndarray,
        spec:   np.ndarray,
        *,
        db_scale: bool,
        cmap_name: str,
        width:    int,
        height:   int,
        title:    str,
    ) -> np.ndarray:
        """Render the polar heatmap to a BGR ``uint8`` array.

        Closes the figure in the ``finally`` block so a long-running
        flow doesn't leak figures across frames (parity with the
        rest of the matplotlib-based viz nodes).
        """
        fig = plt.figure(
            figsize=(width / _RENDER_DPI, height / _RENDER_DPI),
            dpi=_RENDER_DPI,
        )
        try:
            ax = fig.add_subplot(111, projection="polar")
            # Wrap angles + spectrum so the polar plot closes back to
            # 2π without a visible seam at θ = 0.
            theta_closed = np.concatenate([thetas, [2.0 * np.pi]])
            spec_closed  = np.vstack([spec, spec[:1]])
            T, R = np.meshgrid(theta_closed, freqs, indexing="xy")
            mesh = ax.pcolormesh(T, R, spec_closed.T, cmap=cmap_name, shading="auto")
            ax.set_theta_zero_location("N")
            ax.set_theta_direction(-1)
            if title:
                ax.set_title(title)
            cbar = fig.colorbar(mesh, ax=ax, pad=0.1, shrink=0.8)
            cbar.set_label("dB" if db_scale else "amplitude")
            fig.tight_layout(pad=0.4)
            fig.canvas.draw()
            rgba = np.asarray(fig.canvas.buffer_rgba())
            return cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGR)
        finally:
            plt.close(fig)

from __future__ import annotations

from enum import IntEnum

import numpy as np
import pandas as pd
from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase
from core.params import BoolParam, EnumParam, FloatParam
from core.port import InputPort, OutputPort

#: Tiny floor under the dB conversion so a silent column doesn't blow
#: up to ``-inf``. Scaled relative to the global peak so the dynamic
#: range stays meaningful regardless of input magnitude.
_DB_FLOOR_REL: float = 1e-6

#: Name of the frequency-axis index on the output DataFrame.
INDEX_NAME_FREQUENCY: str = "frequency_hz"


class WindowKind(IntEnum):
    """Per-column windowing applied before the FFT.

    A short windowed segment (typical SlidingWindow output) leaks
    spectrally without a tapering window; a Hann window suppresses
    that. ``NONE`` is available for cases where the user has already
    windowed upstream or wants the raw rectangular-window response.
    """
    NONE = 0
    HANN = 1


class Spectrum(NodeBase):
    """Per-column magnitude FFT of a :data:`IoDataType.DATASET`.

    Computes ``|F|`` (or ``20·log10|F|`` when ``db_scale=True``) for
    every column of the input. The output is a DATASET whose row index
    is frequency in Hz (``index.name = "frequency_hz"``) and whose
    column names match the input — so an N-channel time series produces
    an N-channel spectrum that downstream visualisers
    (:class:`PlotSeries`, :class:`PolarHeatmap`) can render directly.

    Conventions:

    * ``sample_rate`` (Hz) sets the frequency axis: ``rfftfreq(n, 1/fs)``.
    * ``freq_max = 0`` keeps the full Nyquist range; a positive value
      clips the radial axis to the band of interest.
    * ``window = HANN`` tapers each column before the FFT to suppress
      spectral leakage on short segments (the typical SlidingWindow
      consumer).
    * ``df.attrs`` from the input is forwarded so per-column annotations
      (e.g. :attr:`directional_projection.ATTR_THETAS_RAD`) survive the
      transform.
    """

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
    freq_max = FloatParam(
        0.0,
        min=0.0,
        constant=True,
        unit="Hz",
        description=(
            "Upper frequency on the output. ``0`` keeps the full "
            "Nyquist range; lower values clip to the band of interest."
        ),
    )
    db_scale = BoolParam(
        True,
        constant=True,
        description=(
            "When True, output ``20·log10|F|`` for wide-dynamic-range "
            "spectra. Linear magnitude when False."
        ),
    )
    window = EnumParam(
        WindowKind,
        WindowKind.HANN,
        constant=True,
        description=(
            "Tapering applied to each column before the FFT. HANN "
            "suppresses spectral leakage on short segments; NONE "
            "uses the raw rectangular window."
        ),
    )

    def __init__(self) -> None:
        super().__init__("Spectrum", section="Frequency")
        self._sample_rate: float
        self._freq_max:    float
        self._db_scale:    bool
        self._window:      WindowKind
        self._add_input(InputPort("dataset", {IoDataType.DATASET}))
        self._add_output(OutputPort("dataset", {IoDataType.DATASET}))
        self._apply_default_params()

    @override
    def process_impl(self) -> None:
        in_io = self.inputs[0].data
        df: pd.DataFrame = in_io.payload
        if len(df) < 2 or len(df.columns) == 0:
            # Too few rows to FFT, or no columns. Emit an empty frame
            # of the right shape so downstream consumers can keep up.
            out_df = pd.DataFrame(
                {col: np.array([], dtype=np.float64) for col in df.columns},
            )
            out_df.index = pd.Index(
                np.array([], dtype=np.float64), name=INDEX_NAME_FREQUENCY,
            )
            out_df.attrs = dict(df.attrs)
            self.outputs[0].send(in_io.clone(payload=out_df))
            return

        freqs, magnitudes = self._compute(
            df.to_numpy(dtype=np.float64),
            self._sample_rate,
            self._window,
        )
        if self._freq_max > 0.0:
            mask = freqs <= self._freq_max
            freqs = freqs[mask]
            magnitudes = magnitudes[mask]
        if self._db_scale:
            magnitudes = self._to_db(magnitudes)

        out_df = pd.DataFrame(magnitudes, columns=df.columns)
        out_df.index = pd.Index(freqs, name=INDEX_NAME_FREQUENCY)
        out_df.attrs = dict(df.attrs)
        self.outputs[0].send(in_io.clone(payload=out_df))

    # ── Pure helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _compute(
        data: np.ndarray, sample_rate: float, window: WindowKind,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Return ``(freqs, magnitudes)`` for the per-column rfft.

        ``data`` shape ``(n_samples, n_columns)``; ``magnitudes``
        shape ``(n_freq, n_columns)`` (linear magnitude); ``freqs``
        shape ``(n_freq,)`` in Hz.
        """
        n = data.shape[0]
        if window is WindowKind.HANN:
            taper = np.hanning(n)[:, None]
            data = data * taper
        spec = np.abs(np.fft.rfft(data, axis=0))
        freqs = np.fft.rfftfreq(n, d=1.0 / sample_rate)
        return freqs, spec

    @staticmethod
    def _to_db(magnitudes: np.ndarray) -> np.ndarray:
        """Convert a linear magnitude array to dB with a relative
        floor. Silent cells clip to ``peak·_DB_FLOOR_REL`` so the
        peak-to-floor distance stays at ``120 dB`` regardless of the
        input scale, and ``-inf`` never reaches downstream renderers."""
        peak = float(np.max(magnitudes)) if magnitudes.size else 0.0
        floor = max(peak * _DB_FLOOR_REL, 1e-12)
        return 20.0 * np.log10(np.maximum(magnitudes, floor))

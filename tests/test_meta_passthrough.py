"""Verify image / dataset / scalar filters propagate IoMeta to their outputs.

A pre-existing bug in many filters constructed fresh ``IoData`` envelopes
without forwarding the upstream meta — so ``source_path`` (stamped by
``DirectorySource`` and friends) silently disappeared one hop downstream
and a ``$source_stem$`` filename template a few nodes later collapsed to
a single overwriting filename.

These tests pin the fix per filter: every output's :class:`IoMeta` must
still carry the upstream ``source_path``. ``frame_index`` is *not*
asserted here — :meth:`core.port.OutputPort.send` deliberately
overwrites it with the port's per-emit counter on the way out, so
checking it would test the framework's stamp behaviour, not the
filter's meta forwarding.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from core.io_data import IoData, IoMeta
from nodes.filters.adaptive_gaussian_threshold import AdaptiveGaussianThreshold
from nodes.filters.add_index_column import AddIndexColumn
from nodes.filters.apply_colormap import ApplyColormap
from nodes.filters.clamp import Clamp
from nodes.filters.fft2d import Fft2D
from nodes.filters.grayscale import Grayscale
from nodes.filters.hsl_split import HslSplit
from nodes.filters.hsv_split import HsvSplit
from nodes.filters.inverse_fft2d import InverseFft2D
from nodes.filters.mosaic import Mosaic
from nodes.filters.plot_xy import PlotXY
from nodes.filters.rgba_split import RgbaSplit
from nodes.filters.subpixel_mosaic import SubpixelMosaic


_PROBE_PATH = Path("ship.jpg")


def _meta() -> IoMeta:
    """Probe meta carrying a distinctive ``source_path`` so the
    assertions catch a regression that drops it during the filter's
    output construction."""
    return IoMeta(source_path=_PROBE_PATH)


def _assert_carries_meta(out: IoData) -> None:
    assert out is not None
    assert out.meta["source_path"] == _PROBE_PATH


# ── 1-input image filters ─────────────────────────────────────────────────────

def test_hsv_split_propagates_meta_on_every_output() -> None:
    node = HsvSplit()
    image = np.full((3, 4, 3), (10, 20, 200), dtype=np.uint8)
    node.inputs[0].receive(IoData.from_image(image, meta=_meta()))
    for port in node.outputs:
        _assert_carries_meta(port.last_emitted)


def test_hsl_split_propagates_meta_on_every_output() -> None:
    node = HslSplit()
    image = np.full((3, 4, 3), (10, 20, 200), dtype=np.uint8)
    node.inputs[0].receive(IoData.from_image(image, meta=_meta()))
    for port in node.outputs:
        _assert_carries_meta(port.last_emitted)


def test_rgba_split_propagates_meta_on_every_output() -> None:
    node = RgbaSplit()
    image = np.full((3, 4, 3), (10, 20, 200), dtype=np.uint8)
    node.inputs[0].receive(IoData.from_image(image, meta=_meta()))
    for port in node.outputs:
        _assert_carries_meta(port.last_emitted)


def test_grayscale_propagates_meta() -> None:
    node = Grayscale()
    image = np.full((3, 4, 3), 128, dtype=np.uint8)
    node.inputs[0].receive(IoData.from_image(image, meta=_meta()))
    _assert_carries_meta(node.outputs[0].last_emitted)


def test_apply_colormap_propagates_meta() -> None:
    node = ApplyColormap()
    grey = np.tile(np.arange(16, dtype=np.uint8), (4, 1))
    node.inputs[0].receive(IoData.from_greyscale(grey, meta=_meta()))
    _assert_carries_meta(node.outputs[0].last_emitted)


def test_adaptive_gaussian_threshold_propagates_meta() -> None:
    node = AdaptiveGaussianThreshold()
    grey = np.full((128, 128), 128, dtype=np.uint8)
    node.inputs[0].receive(IoData.from_greyscale(grey, meta=_meta()))
    _assert_carries_meta(node.outputs[0].last_emitted)


def test_subpixel_mosaic_propagates_meta() -> None:
    node = SubpixelMosaic()
    image = np.full((4, 4, 3), 64, dtype=np.uint8)
    node.inputs[0].receive(IoData.from_image(image, meta=_meta()))
    _assert_carries_meta(node.outputs[0].last_emitted)


# ── FFT round-trip ────────────────────────────────────────────────────────────

def test_fft2d_propagates_meta_on_both_outputs() -> None:
    node = Fft2D()
    grey = np.tile(np.arange(16, dtype=np.uint8), (16, 1))
    node.inputs[0].receive(IoData.from_greyscale(grey, meta=_meta()))
    spectrum_out, magnitude_out = node.outputs
    _assert_carries_meta(spectrum_out.last_emitted)
    _assert_carries_meta(magnitude_out.last_emitted)


def test_inverse_fft2d_propagates_meta() -> None:
    node = InverseFft2D()
    spectrum = np.fft.fftshift(
        np.fft.fft2(np.full((8, 8), 128, dtype=np.uint8).astype(np.float64))
    )
    node.inputs[0].receive(IoData.from_matrix(spectrum, meta=_meta()))
    _assert_carries_meta(node.outputs[0].last_emitted)


# ── Scalar / dataset filters ──────────────────────────────────────────────────

def test_clamp_propagates_meta() -> None:
    node = Clamp()
    node.inputs[0].receive(IoData.from_scalar(0.5, meta=_meta()))
    _assert_carries_meta(node.outputs[0].last_emitted)


def test_add_index_column_propagates_meta() -> None:
    node = AddIndexColumn()
    df = pd.DataFrame({"v": [1.0, 2.0, 3.0]})
    node.inputs[0].receive(IoData.from_dataset(df, meta=_meta()))
    _assert_carries_meta(node.outputs[0].last_emitted)


def test_plot_xy_propagates_meta() -> None:
    node = PlotXY()
    df = pd.DataFrame({"x": np.arange(8), "y": np.arange(8) ** 2})
    node.inputs[0].receive(IoData.from_dataset(df, meta=_meta()))
    _assert_carries_meta(node.outputs[0].last_emitted)


# ── Multi-input: Mosaic ───────────────────────────────────────────────────────

def test_mosaic_takes_meta_from_first_non_empty_cell() -> None:
    """Mosaic builds one output from many inputs; the contract is that
    it forwards meta from the first non-empty cell of the first row.
    A bulk-FFT-style flow where every input traces back to the same
    upstream frame keeps source_path on the way out, which is what the
    FileSink's ``$source_stem$`` template needs to land per-frame
    filenames."""
    node = Mosaic()
    # Default layout is "1,2;3,4" — four inputs across two rows. Feed
    # the first cell with the meta-bearing frame; leave the rest with
    # plain (no-meta) frames so a regression that picks meta from the
    # wrong cell would lose source_path on the output.
    node.inputs[0].receive(IoData.from_image(
        np.full((4, 4, 3), 100, dtype=np.uint8), meta=_meta(),
    ))
    for port in node.inputs[1:]:
        port.receive(IoData.from_image(
            np.full((4, 4, 3), 200, dtype=np.uint8),
        ))
    _assert_carries_meta(node.outputs[0].last_emitted)

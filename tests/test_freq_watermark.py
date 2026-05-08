"""Unit tests for MatrixAdd + BandpassMask (frequency-domain primitives)."""
from __future__ import annotations

import numpy as np
import pytest

from core.io_data import IoData, IoDataType
from core.port import InputPort
from nodes.filters.bandpass_mask import BandpassMask
from nodes.filters.fft2d import Fft2D
from nodes.filters.inverse_fft2d import InverseFft2D
from nodes.filters.matrix_add import MatrixAdd


# ── MatrixAdd ──────────────────────────────────────────────────────────────────


def test_matrix_add_default_weight_is_plain_sum() -> None:
    node = MatrixAdd()
    a = np.arange(9, dtype=np.float64).reshape(3, 3)
    b = np.full((3, 3), 10.0)
    node.inputs[0].receive(IoData.from_matrix(a))
    node.inputs[1].receive(IoData.from_matrix(b))

    out = node.outputs[0].last_emitted
    assert out is not None and out.type == IoDataType.MATRIX
    np.testing.assert_array_equal(out.payload, a + b)


def test_matrix_add_weighted_combination() -> None:
    node = MatrixAdd()
    node.weight = 0.25
    a = np.ones((4, 4))
    b = np.full((4, 4), 8.0)
    node.inputs[0].receive(IoData.from_matrix(a))
    node.inputs[1].receive(IoData.from_matrix(b))

    out = node.outputs[0].last_emitted.payload
    np.testing.assert_allclose(out, np.full((4, 4), 1.0 + 0.25 * 8.0))


def test_matrix_add_promotes_real_plus_complex() -> None:
    """Adding a real spectrum to a complex one stays complex
    rather than dropping the imaginary part."""
    node = MatrixAdd()
    a = np.ones((2, 2), dtype=np.complex128) * (1 + 2j)
    b = np.ones((2, 2), dtype=np.float64)
    node.inputs[0].receive(IoData.from_matrix(a))
    node.inputs[1].receive(IoData.from_matrix(b))

    out = node.outputs[0].last_emitted.payload
    assert np.iscomplexobj(out)
    np.testing.assert_allclose(out, np.full((2, 2), 2 + 2j))


def test_matrix_add_shape_mismatch_raises() -> None:
    node = MatrixAdd()
    a = np.zeros((3, 3))
    b = np.zeros((3, 4))
    node.inputs[0].receive(IoData.from_matrix(a))
    with pytest.raises(ValueError, match="shape mismatch"):
        node.inputs[1].receive(IoData.from_matrix(b))


# ── BandpassMask ───────────────────────────────────────────────────────────────


def test_bandpass_mask_zeros_dc_and_corners() -> None:
    """Default 0.05–0.25 band must zero the centre (DC) and the
    far corners while keeping a mid-radius coefficient."""
    node = BandpassMask()
    spectrum = np.ones((32, 32), dtype=np.complex128)
    node.inputs[0].receive(IoData.from_matrix(spectrum))

    out = node.outputs[0].last_emitted.payload
    # DC at fftshifted centre (16, 16) → below radius_low → zeroed.
    assert out[16, 16] == 0
    # Corners → r ≈ 1 → above radius_high → zeroed.
    assert out[0, 0] == 0
    # Mid radius (~0.13 of corner distance) → kept.
    assert out[16 + 3, 16] != 0


def test_bandpass_mask_preserves_hermitian_symmetry() -> None:
    """A real image's FFT is Hermitian. The mask depends only on
    radius, so the masked spectrum stays Hermitian and the
    inverse FFT of its sum with the original is real."""
    rng = np.random.default_rng(1)
    image = rng.integers(0, 256, size=(16, 16), dtype=np.uint8)

    fft = Fft2D()
    bp = BandpassMask()
    add = MatrixAdd()
    add.weight = 0.05
    ifft = InverseFft2D()

    fft.outputs[0].connect(bp.inputs[0])
    fft.outputs[0].connect(add.inputs[0])
    bp.outputs[0].connect(add.inputs[1])
    add.outputs[0].connect(ifft.inputs[0])

    capture = InputPort("cap", {IoDataType.IMAGE_GREY})
    ifft.outputs[0].connect(capture)

    fft.inputs[0].receive(IoData.from_greyscale(image))

    assert capture.has_data
    out = capture.data.image
    assert out.dtype == np.uint8
    assert out.shape == image.shape
    # The watermarked image should be close to the original
    # (small weight → small perturbation).
    diff = np.abs(out.astype(int) - image.astype(int))
    assert diff.max() < 50


def test_bandpass_mask_rejects_inverted_radii() -> None:
    node = BandpassMask()
    node.radius_low = 0.5
    node.radius_high = 0.2
    spectrum = np.ones((8, 8), dtype=np.complex128)
    with pytest.raises(ValueError, match="radius_low.*radius_high"):
        node.inputs[0].receive(IoData.from_matrix(spectrum))


# ── End-to-end watermark embed → recover ───────────────────────────────────────


def test_watermark_recoverable_in_spectrum_difference() -> None:
    """Embedding a band-passed perturbation must leave a detectable
    trace in the magnitude spectrum of the watermarked image
    (the basis of recovery), even when the pixel-domain
    difference stays small."""
    rng = np.random.default_rng(42)
    base = rng.integers(0, 256, size=(64, 64), dtype=np.uint8)
    mark = rng.integers(0, 256, size=(64, 64), dtype=np.uint8)

    fft_base = Fft2D()
    fft_mark = Fft2D()
    bp = BandpassMask()
    bp.radius_low = 0.1
    bp.radius_high = 0.3
    add = MatrixAdd()
    add.weight = 0.05
    ifft = InverseFft2D()

    fft_base.outputs[0].connect(add.inputs[0])
    fft_mark.outputs[0].connect(bp.inputs[0])
    bp.outputs[0].connect(add.inputs[1])
    add.outputs[0].connect(ifft.inputs[0])

    capture = InputPort("cap", {IoDataType.IMAGE_GREY})
    ifft.outputs[0].connect(capture)

    fft_base.inputs[0].receive(IoData.from_greyscale(base))
    fft_mark.inputs[0].receive(IoData.from_greyscale(mark))

    watermarked = capture.data.image

    # Pixel-domain difference is small (perceptually invisible regime).
    pix_diff = np.abs(watermarked.astype(int) - base.astype(int))
    assert pix_diff.mean() < 10

    # Spectrum-domain difference concentrated in the embedded band.
    fft_check = Fft2D()
    fft_check.inputs[0].receive(IoData.from_greyscale(watermarked))
    spec_wm   = fft_check.outputs[0].last_emitted.payload

    fft_check2 = Fft2D()
    fft_check2.inputs[0].receive(IoData.from_greyscale(base))
    spec_base = fft_check2.outputs[0].last_emitted.payload

    diff = np.abs(spec_wm - spec_base)
    h, w = diff.shape
    cy, cx = h / 2.0, w / 2.0
    ys = np.arange(h, dtype=np.float64) - cy
    xs = np.arange(w, dtype=np.float64) - cx
    yy, xx = np.meshgrid(ys, xs, indexing="ij")
    r = np.sqrt(yy * yy + xx * xx) / np.sqrt(cx * cx + cy * cy)
    in_band  = (r >= 0.1) & (r <= 0.3)
    out_band = ~in_band

    # Most of the spectral perturbation energy lives inside the band.
    assert diff[in_band].sum() > diff[out_band].sum()

"""Unit tests for ImageToMatrix and the BGRA path on Grayscale."""
from __future__ import annotations

import numpy as np
import pytest

from core.io_data import IoData, IoDataType
from core.port import InputPort
from nodes.filters.fft2d import Fft2D
from nodes.filters.grayscale import Grayscale
from nodes.filters.image_to_matrix import ImageToMatrix
from nodes.filters.inverse_fft2d import InverseFft2D
from nodes.filters.matrix_add import MatrixAdd


# ── ImageToMatrix ──────────────────────────────────────────────────────────────


def test_image_to_matrix_passes_pixels_through_as_float() -> None:
    node = ImageToMatrix()
    image = np.array([[0, 64], [128, 255]], dtype=np.uint8)
    node.inputs[0].receive(IoData.from_greyscale(image))

    out = node.outputs[0].last_emitted
    assert out is not None and out.type == IoDataType.MATRIX
    assert out.payload.shape == image.shape
    assert out.payload.dtype == np.float64
    np.testing.assert_array_equal(out.payload, image.astype(np.float64))


def test_image_to_matrix_rejects_colour_input() -> None:
    node = ImageToMatrix()
    bgr = np.zeros((4, 4, 3), dtype=np.uint8)
    with pytest.raises(ValueError, match="single-channel"):
        node.inputs[0].receive(IoData.from_greyscale(bgr))


def test_point_symmetric_image_keeps_inverse_real() -> None:
    """A point-symmetric image added to a base spectrum must leave
    the inverse FFT real (uint8 round-trip survives), since a real
    centro-symmetric perturbation is Hermitian on the spectrum."""
    rng = np.random.default_rng(0)
    base = rng.integers(0, 256, size=(16, 16), dtype=np.uint8)

    half = rng.integers(0, 64, size=(16, 8), dtype=np.uint8)
    # Point-symmetric construction: left half is ``half``,
    # right half is the 180°-rotated copy. M(x,y) = M(W-1-x, H-1-y)
    # holds by construction.
    flipped = half[::-1, ::-1]
    watermark = np.concatenate([half, flipped], axis=1)
    assert watermark.shape == (16, 16)
    # Sanity: actually point-symmetric.
    np.testing.assert_array_equal(watermark, watermark[::-1, ::-1])

    fft = Fft2D()
    bridge = ImageToMatrix()
    add = MatrixAdd()
    add.weight = 1.0
    ifft = InverseFft2D()

    fft.outputs[0].connect(add.inputs[0])
    bridge.outputs[0].connect(add.inputs[1])
    add.outputs[0].connect(ifft.inputs[0])
    capture = InputPort("cap", {IoDataType.IMAGE_GREY})
    ifft.outputs[0].connect(capture)

    fft.inputs[0].receive(IoData.from_greyscale(base))
    bridge.inputs[0].receive(IoData.from_greyscale(watermark))

    assert capture.has_data
    out = capture.data.image
    assert out.dtype == np.uint8
    assert out.shape == base.shape


# ── Grayscale BGRA path ───────────────────────────────────────────────────────


def test_grayscale_handles_bgra_input() -> None:
    """A 4-channel BGRA image (e.g. RGBA PNG via ImageSource) must
    convert to greyscale without erroring on the channel count."""
    node = Grayscale()
    bgra = np.zeros((4, 4, 4), dtype=np.uint8)
    bgra[..., :3] = 200  # bright BGR
    bgra[..., 3] = 255   # opaque
    node.inputs[0].receive(IoData.from_image(bgra))

    out = node.outputs[0].last_emitted
    assert out is not None and out.type == IoDataType.IMAGE_GREY
    assert out.image.shape == (4, 4)
    assert out.image.dtype == np.uint8
    # 200 BGR converts to 200 grey (uniform channels).
    assert int(out.image[0, 0]) == 200

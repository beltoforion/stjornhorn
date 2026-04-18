"""Unit tests for the filter nodes ported from OCVL."""
from __future__ import annotations

import cv2
import numpy as np
import pytest

from core.io_data import IoData
from nodes.filters.adaptive_gaussian_threshold import AdaptiveGaussianThreshold
from nodes.filters.dither import Dither, DitherMethod
from nodes.filters.median import Median
from nodes.filters.normalize import Normalize
from nodes.filters.scale import Scale
from nodes.filters.shift import Shift


def _bgr(h: int = 32, w: int = 32, value: int = 128) -> np.ndarray:
    return np.full((h, w, 3), value, dtype=np.uint8)


def _gradient(h: int = 16, w: int = 16) -> np.ndarray:
    """Deterministic grayscale gradient useful for dither tests."""
    row = np.linspace(0, 255, w, dtype=np.uint8)
    return np.tile(row, (h, 1))


def _run(node, image: np.ndarray) -> np.ndarray:
    """Feed ``image`` into ``node``'s first input and return the first output."""
    node.inputs[0].receive(IoData.from_image(image))
    out = node.outputs[0].last_emitted
    assert out is not None, "node did not emit on output 0"
    return out.image


# ── Shift ─────────────────────────────────────────────────────────────────────

def test_shift_translates_image_by_offset() -> None:
    image = np.zeros((8, 8, 3), dtype=np.uint8)
    image[0, 0] = (255, 255, 255)

    node = Shift()
    node.offset_x = 2
    node.offset_y = 1
    out = _run(node, image)

    assert out.shape == image.shape
    np.testing.assert_array_equal(out[1, 2], (255, 255, 255))
    np.testing.assert_array_equal(out[0, 0], (0, 0, 0))


def test_shift_defaults_to_identity() -> None:
    image = _bgr(8, 8, 200)
    out = _run(Shift(), image)
    np.testing.assert_array_equal(out, image)


# ── Scale ─────────────────────────────────────────────────────────────────────

def test_scale_doubles_dimensions_at_200_percent() -> None:
    image = _bgr(10, 20)

    node = Scale()
    node.scale_percent = 200
    out = _run(node, image)

    assert out.shape == (20, 40, 3)


def test_scale_halves_dimensions_at_50_percent() -> None:
    image = _bgr(10, 20)

    node = Scale()
    node.scale_percent = 50
    out = _run(node, image)

    assert out.shape == (5, 10, 3)


def test_scale_rejects_invalid_interpolation() -> None:
    node = Scale()
    with pytest.raises(ValueError):
        node.interpolation = 99


def test_scale_rejects_non_positive_percent() -> None:
    node = Scale()
    with pytest.raises(ValueError):
        node.scale_percent = 0


# ── Median ────────────────────────────────────────────────────────────────────

def test_median_blurs_single_salt_pixel() -> None:
    image = np.zeros((8, 8, 3), dtype=np.uint8)
    image[4, 4] = (255, 255, 255)

    out = _run(Median(), image)

    # A single white pixel in a field of black vanishes under a 3×3 median.
    assert out[4, 4].tolist() == [0, 0, 0]


def test_median_coerces_even_size_to_next_odd() -> None:
    node = Median()
    node.size = 4
    assert node.size == 5


def test_median_rejects_non_positive_size() -> None:
    node = Median()
    with pytest.raises(ValueError):
        node.size = 0


# ── Normalize ─────────────────────────────────────────────────────────────────

def test_normalize_matches_cv2_equalize_hist_per_channel() -> None:
    rng = np.random.default_rng(0)
    image = rng.integers(0, 128, size=(16, 16, 3), dtype=np.uint8)

    out = _run(Normalize(), image)
    expected = cv2.merge([cv2.equalizeHist(c) for c in cv2.split(image)])

    np.testing.assert_array_equal(out, expected)


def test_normalize_passes_through_grayscale_input() -> None:
    rng = np.random.default_rng(1)
    image = rng.integers(0, 128, size=(16, 16), dtype=np.uint8)

    out = _run(Normalize(), image)
    np.testing.assert_array_equal(out, cv2.equalizeHist(image))


# ── AdaptiveGaussianThreshold ─────────────────────────────────────────────────

def test_agauss_threshold_produces_greyscale_binary_output() -> None:
    rng = np.random.default_rng(2)
    image = rng.integers(0, 256, size=(128, 128, 3), dtype=np.uint8)

    node = AdaptiveGaussianThreshold()
    out = _run(node, image)

    # Now a single-channel IMAGE_GREY payload.
    assert out.shape == (128, 128)
    assert set(np.unique(out).tolist()).issubset({0, 255})


def test_agauss_threshold_coerces_even_block_size() -> None:
    node = AdaptiveGaussianThreshold()
    node.block_size = 50
    assert node.block_size == 51


def test_agauss_threshold_rejects_tiny_block_size() -> None:
    node = AdaptiveGaussianThreshold()
    with pytest.raises(ValueError):
        node.block_size = 1


# ── Dither ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("method", list(DitherMethod))
def test_dither_produces_greyscale_binary_output(method: DitherMethod) -> None:
    image = _gradient(h=8, w=8)

    node = Dither()
    node.method = int(method)
    out = _run(node, image)

    # Dither emits a single-channel IMAGE_GREY payload.
    assert out.shape == (8, 8)
    assert set(np.unique(out).tolist()).issubset({0, 255})


def test_dither_accepts_bgr_input() -> None:
    # Gradient broadcast to 3 channels — the node should greyscale it.
    gray = _gradient(h=8, w=8)
    bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

    node = Dither()
    node.method = int(DitherMethod.BAYER4)
    out = _run(node, bgr)

    assert out.shape == (8, 8)
    assert set(np.unique(out).tolist()).issubset({0, 255})


def test_dither_rejects_unknown_method() -> None:
    node = Dither()
    with pytest.raises(ValueError):
        node.method = 99

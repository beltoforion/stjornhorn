"""Tests for the filter nodes added in v0.1.20.

Covers Flip, Crop, Rotate, Gaussian Blur, Invert, Frame Difference,
Temporal Mean and Temporal Median. Same pattern as ``test_filters.py``
— a private ``_run`` helper feeds a single ``IoData`` into the node's
first input and reads the first output back.
"""
from __future__ import annotations

import numpy as np
import pytest

from core.io_data import IoData
from nodes.filters.crop import Crop
from nodes.filters.flip import Flip, FlipMode
from nodes.filters.frame_difference import FrameDifference
from nodes.filters.gaussian_blur import GaussianBlur
from nodes.filters.invert import Invert
from nodes.filters.rotate import Rotate
from nodes.filters.temporal_mean import TemporalMean
from nodes.filters.temporal_median import TemporalMedian


def _bgr(h: int = 16, w: int = 16, value: int = 100) -> np.ndarray:
    return np.full((h, w, 3), value, dtype=np.uint8)


def _grey(h: int = 16, w: int = 16, value: int = 100) -> np.ndarray:
    return np.full((h, w), value, dtype=np.uint8)


def _run(node, image: np.ndarray) -> np.ndarray:
    node.inputs[0].receive(IoData.from_image(image))
    out = node.outputs[0].last_emitted
    assert out is not None, "node did not emit on output 0"
    return out.image


# ── Flip ──────────────────────────────────────────────────────────────────────

def test_flip_horizontal_mirrors_left_right() -> None:
    image = np.zeros((4, 4, 3), dtype=np.uint8)
    image[0, 0] = (255, 255, 255)

    node = Flip()
    node.mode = FlipMode.HORIZONTAL
    out = _run(node, image)

    np.testing.assert_array_equal(out[0, 3], (255, 255, 255))
    np.testing.assert_array_equal(out[0, 0], (0, 0, 0))


def test_flip_vertical_mirrors_top_bottom() -> None:
    image = np.zeros((4, 4, 3), dtype=np.uint8)
    image[0, 0] = (255, 255, 255)

    node = Flip()
    node.mode = FlipMode.VERTICAL
    out = _run(node, image)

    np.testing.assert_array_equal(out[3, 0], (255, 255, 255))
    np.testing.assert_array_equal(out[0, 0], (0, 0, 0))


def test_flip_both_is_180_rotation() -> None:
    image = np.zeros((4, 4, 3), dtype=np.uint8)
    image[0, 0] = (255, 255, 255)

    node = Flip()
    node.mode = FlipMode.BOTH
    out = _run(node, image)

    np.testing.assert_array_equal(out[3, 3], (255, 255, 255))
    np.testing.assert_array_equal(out[0, 0], (0, 0, 0))


def test_flip_mode_setter_rejects_invalid_value() -> None:
    node = Flip()
    with pytest.raises(ValueError):
        node.mode = 99


# ── Crop ──────────────────────────────────────────────────────────────────────

def test_crop_returns_requested_roi() -> None:
    image = np.arange(8 * 8 * 3, dtype=np.uint8).reshape(8, 8, 3)
    node = Crop()
    node.x, node.y, node.width, node.height = 2, 1, 4, 3
    out = _run(node, image)

    assert out.shape == (3, 4, 3)
    np.testing.assert_array_equal(out, image[1:4, 2:6])


def test_crop_clamps_oversized_roi_to_input_bounds() -> None:
    image = _bgr(8, 8, 50)
    node = Crop()
    node.x, node.y, node.width, node.height = 4, 4, 100, 100
    out = _run(node, image)

    assert out.shape == (4, 4, 3)


def test_crop_produces_at_least_one_pixel_for_off_canvas_roi() -> None:
    image = _bgr(8, 8)
    node = Crop()
    node.x, node.y, node.width, node.height = 50, 50, 4, 4
    out = _run(node, image)

    assert out.size > 0
    assert out.shape == (1, 1, 3)


def test_crop_rejects_zero_or_negative_size() -> None:
    node = Crop()
    with pytest.raises(ValueError):
        node.width = 0
    with pytest.raises(ValueError):
        node.height = -3


# ── Rotate ────────────────────────────────────────────────────────────────────

def test_rotate_zero_degrees_is_identity_when_expand_off() -> None:
    image = _bgr(10, 20, 77)
    node = Rotate()
    node.angle = 0.0
    node.expand = False
    out = _run(node, image)

    assert out.shape == image.shape
    np.testing.assert_array_equal(out, image)


def test_rotate_90_with_expand_swaps_dimensions() -> None:
    image = _bgr(10, 20)
    node = Rotate()
    node.angle = 90.0
    node.expand = True
    out = _run(node, image)

    # 90° rotation of a 20×10 (W×H) image yields 10×20.
    assert out.shape == (20, 10, 3)


def test_rotate_keeps_input_dimensions_when_expand_off() -> None:
    image = _bgr(12, 24)
    node = Rotate()
    node.angle = 30.0
    node.expand = False
    out = _run(node, image)

    assert out.shape == image.shape


# ── Gaussian Blur ─────────────────────────────────────────────────────────────

def test_gaussian_blur_smooths_high_contrast_edge() -> None:
    image = np.zeros((8, 8, 3), dtype=np.uint8)
    image[:, 4:] = 255

    node = GaussianBlur()
    node.ksize = 5
    node.sigma = 0.0
    out = _run(node, image)

    # The hard edge column 4 was 255 against a 0 neighbour; after the
    # blur the same column pulls in dark pixels and falls below 255.
    assert int(out[4, 4, 0]) < 255
    assert int(out[4, 4, 0]) > 0


def test_gaussian_blur_even_ksize_is_rounded_up_to_odd() -> None:
    node = GaussianBlur()
    node.ksize = 6
    assert node.ksize == 7


def test_gaussian_blur_rejects_negative_sigma() -> None:
    node = GaussianBlur()
    with pytest.raises(ValueError):
        node.sigma = -1.0


# ── Invert ────────────────────────────────────────────────────────────────────

def test_invert_returns_complement_of_each_pixel() -> None:
    image = _bgr(4, 4, 30)
    out = _run(Invert(), image)

    np.testing.assert_array_equal(out, 255 - image)


def test_invert_passes_through_greyscale_type() -> None:
    node = Invert()
    node.inputs[0].receive(IoData.from_greyscale(_grey(4, 4, 200)))
    emitted = node.outputs[0].last_emitted
    assert emitted is not None
    np.testing.assert_array_equal(emitted.image, 255 - _grey(4, 4, 200))


def test_invert_has_no_params() -> None:
    assert Invert().params == []


# ── Frame Difference ──────────────────────────────────────────────────────────

def test_frame_difference_first_frame_is_all_zero() -> None:
    image = _bgr(4, 4, 100)
    node = FrameDifference()
    node.before_run()
    out = _run(node, image)

    np.testing.assert_array_equal(out, np.zeros_like(image))


def test_frame_difference_emits_absdiff_for_subsequent_frames() -> None:
    a = _bgr(4, 4, 30)
    b = _bgr(4, 4, 90)
    node = FrameDifference()
    node.before_run()

    _run(node, a)
    out = _run(node, b)

    expected = np.full_like(a, 60)
    np.testing.assert_array_equal(out, expected)


def test_frame_difference_resets_buffer_between_runs() -> None:
    node = FrameDifference()
    node.before_run()
    _run(node, _bgr(4, 4, 50))

    node.before_run()
    out = _run(node, _bgr(4, 4, 200))

    # Second run starts cold — first frame again emits zeros, not the
    # difference against the previous run's leftover frame.
    np.testing.assert_array_equal(out, np.zeros_like(_bgr(4, 4)))


# ── Temporal Mean ─────────────────────────────────────────────────────────────

def test_temporal_mean_first_frame_passes_through() -> None:
    image = _bgr(4, 4, 100)
    node = TemporalMean()
    node.window = 3
    node.before_run()
    out = _run(node, image)

    np.testing.assert_array_equal(out, image)


def test_temporal_mean_averages_buffered_frames() -> None:
    node = TemporalMean()
    node.window = 3
    node.before_run()

    _run(node, _bgr(4, 4, 30))
    _run(node, _bgr(4, 4, 90))
    out = _run(node, _bgr(4, 4, 150))

    # Mean of {30, 90, 150} == 90 across every pixel/channel.
    expected = _bgr(4, 4, 90)
    np.testing.assert_array_equal(out, expected)


def test_temporal_mean_drops_oldest_when_window_full() -> None:
    node = TemporalMean()
    node.window = 2
    node.before_run()

    _run(node, _bgr(4, 4, 0))
    _run(node, _bgr(4, 4, 100))
    out = _run(node, _bgr(4, 4, 200))

    # Only the last two are in the window: mean(100, 200) == 150.
    np.testing.assert_array_equal(out, _bgr(4, 4, 150))


def test_temporal_mean_rejects_zero_window() -> None:
    with pytest.raises(ValueError):
        TemporalMean().window = 0


# ── Temporal Median ───────────────────────────────────────────────────────────

def test_temporal_median_picks_middle_value() -> None:
    node = TemporalMedian()
    node.window = 3
    node.before_run()

    _run(node, _bgr(4, 4, 10))
    _run(node, _bgr(4, 4, 200))
    out = _run(node, _bgr(4, 4, 50))

    # Median of {10, 200, 50} == 50 — robust against the 200 outlier
    # that would have biased a mean to ~86.
    np.testing.assert_array_equal(out, _bgr(4, 4, 50))


def test_temporal_median_first_frame_passes_through() -> None:
    image = _bgr(4, 4, 70)
    node = TemporalMedian()
    node.window = 3
    node.before_run()
    out = _run(node, image)

    np.testing.assert_array_equal(out, image)

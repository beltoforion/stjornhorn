"""Unit tests for the GradientSource node."""
from __future__ import annotations

import numpy as np
import pytest

from core.io_data import IoDataType
from nodes.sources.gradient_source import (
    GradientDirection,
    GradientMode,
    GradientSource,
)


def _emit(node: GradientSource) -> np.ndarray:
    node.process()
    out = node.outputs[0].last_emitted
    assert out is not None
    assert out.type == IoDataType.IMAGE_GREY
    return out.image


def test_default_emits_uint8_grey_image_of_configured_size() -> None:
    node = GradientSource()
    node.width = 64
    node.height = 32
    img = _emit(node)
    assert img.dtype == np.uint8
    assert img.shape == (32, 64)


def test_vertical_centre_row_is_zero_with_band() -> None:
    """With a non-zero band_width, the centre row(s) sit on the plateau."""
    node = GradientSource()
    node.width = 64
    node.height = 65  # odd height, exact centre row
    node.direction = GradientDirection.VERTICAL
    node.band_width = 0.2
    img = _emit(node)
    centre_row = img[32]
    assert centre_row.max() == 0


def test_vertical_outermost_rows_are_max() -> None:
    node = GradientSource()
    node.width = 16
    node.height = 33
    node.direction = GradientDirection.VERTICAL
    node.band_width = 0.0
    img = _emit(node)
    # Top and bottom rows reach the maximum (255).
    assert img[0].max() == 255
    assert img[-1].max() == 255


def test_vertical_is_constant_along_x() -> None:
    """A vertical gradient varies only with Y — every column is identical."""
    node = GradientSource()
    node.width = 32
    node.height = 32
    node.direction = GradientDirection.VERTICAL
    img = _emit(node)
    np.testing.assert_array_equal(img[:, 0], img[:, 31])


def test_horizontal_is_constant_along_y() -> None:
    node = GradientSource()
    node.width = 32
    node.height = 32
    node.direction = GradientDirection.HORIZONTAL
    img = _emit(node)
    np.testing.assert_array_equal(img[0, :], img[31, :])


def test_radial_centre_is_zero_and_corners_are_max() -> None:
    node = GradientSource()
    node.width = 33
    node.height = 33
    node.direction = GradientDirection.RADIAL
    node.band_width = 0.0
    img = _emit(node)
    # Exact centre pixel at (16, 16); distance is 0 → mask is 0.
    assert img[16, 16] == 0
    # Each corner sits at maximum normalised distance → 255.
    assert img[0, 0] == 255
    assert img[0, -1] == 255
    assert img[-1, 0] == 255
    assert img[-1, -1] == 255


def test_band_width_widens_zero_plateau() -> None:
    """Larger band_width → more pixels stay at zero in the centre."""
    a = GradientSource()
    a.width = 64
    a.height = 64
    a.direction = GradientDirection.VERTICAL
    a.band_width = 0.1
    img_a = _emit(a)

    b = GradientSource()
    b.width = 64
    b.height = 64
    b.direction = GradientDirection.VERTICAL
    b.band_width = 0.5
    img_b = _emit(b)

    assert (img_b == 0).sum() > (img_a == 0).sum()


def test_smooth_vs_linear_disagree_in_the_ramp() -> None:
    """The cosine-eased ramp differs from the linear one in mid-ramp."""
    a = GradientSource()
    a.width = 64
    a.height = 64
    a.direction = GradientDirection.VERTICAL
    a.band_width = 0.0
    a.smooth = True
    smooth = _emit(a)

    b = GradientSource()
    b.width = 64
    b.height = 64
    b.direction = GradientDirection.VERTICAL
    b.band_width = 0.0
    b.smooth = False
    linear = _emit(b)

    # Same shape, same endpoints (0 in centre, 255 at the edges) but
    # different intermediate values.
    assert smooth.shape == linear.shape
    assert int(smooth[0, 0]) == int(linear[0, 0])
    assert int(smooth[-1, 0]) == int(linear[-1, 0])
    # Difference somewhere along the ramp.
    assert not np.array_equal(smooth, linear)


def test_invalid_size_raises() -> None:
    node = GradientSource()
    with pytest.raises(ValueError):
        node.width = 0
    with pytest.raises(ValueError):
        node.height = -1


def test_band_width_clamped_to_unit_interval() -> None:
    node = GradientSource()
    node.band_width = -0.5
    assert node.band_width == 0.0
    node.band_width = 5.0
    # Clamped just below 1.0 to keep the ramp denominator positive.
    assert node.band_width < 1.0
    assert node.band_width >= 0.999


def test_direction_setter_accepts_int_and_enum() -> None:
    node = GradientSource()
    node.direction = 1
    assert node.direction == GradientDirection.HORIZONTAL
    node.direction = GradientDirection.RADIAL
    assert node.direction == GradientDirection.RADIAL


def test_direction_setter_rejects_unknown_value() -> None:
    node = GradientSource()
    with pytest.raises(ValueError):
        node.direction = 99


def test_is_reactive_true() -> None:
    """Single-frame source — the editor should re-run on any param edit."""
    assert GradientSource().is_reactive is True


# ── LINEAR mode ───────────────────────────────────────────────────────────────


def test_default_mode_is_symmetric() -> None:
    """Saved flows from before the mode parameter was added must keep
    behaving like a centred double gradient — SYMMETRIC stays the default."""
    assert GradientSource().mode == GradientMode.SYMMETRIC


def test_linear_vertical_runs_top_to_bottom() -> None:
    """One-sided gradient: 0 at the top, 255 at the bottom, no mirror."""
    node = GradientSource()
    node.width = 16
    node.height = 64
    node.direction = GradientDirection.VERTICAL
    node.mode = GradientMode.LINEAR
    node.band_width = 0.0
    img = _emit(node)
    assert img[0].max() == 0
    assert img[-1].max() == 255
    # Centre row sits roughly at the midpoint, *not* at zero (which is
    # the SYMMETRIC behaviour). Cosine-eased ramp passes 0.5 at the
    # midpoint, so the centre value is ~127.
    assert 100 < int(img[32, 0]) < 155


def test_linear_horizontal_runs_left_to_right() -> None:
    node = GradientSource()
    node.width = 64
    node.height = 16
    node.direction = GradientDirection.HORIZONTAL
    node.mode = GradientMode.LINEAR
    node.band_width = 0.0
    img = _emit(node)
    assert img[:, 0].max() == 0
    assert img[:, -1].max() == 255


def test_linear_is_monotonic_along_axis() -> None:
    """A one-sided gradient never decreases as you move along the axis —
    that's the defining property that distinguishes it from a double
    gradient."""
    node = GradientSource()
    node.width = 16
    node.height = 64
    node.direction = GradientDirection.VERTICAL
    node.mode = GradientMode.LINEAR
    node.band_width = 0.0
    node.smooth = False  # linear ramp gives strict monotonicity
    img = _emit(node)
    column = img[:, 0].astype(int)
    diffs = np.diff(column)
    assert (diffs >= 0).all(), f"non-monotonic column: {column.tolist()}"


def test_linear_band_width_acts_as_leading_dead_zone() -> None:
    """In LINEAR mode, ``band_width`` carves out a flat zero region at
    the *start* of the axis (not centred), then the ramp covers the
    rest."""
    node = GradientSource()
    node.width = 16
    node.height = 100
    node.direction = GradientDirection.VERTICAL
    node.mode = GradientMode.LINEAR
    node.band_width = 0.5  # first 50% of rows stay at 0
    node.smooth = False
    img = _emit(node)
    # First half of rows are within the dead zone -> all zero.
    assert img[:50].max() == 0
    # Last row reaches the maximum.
    assert img[-1].max() == 255


def test_radial_ignores_mode() -> None:
    """RADIAL has no meaningful linear variant — selecting LINEAR must
    produce the same output as SYMMETRIC."""
    sym = GradientSource()
    sym.width = 33
    sym.height = 33
    sym.direction = GradientDirection.RADIAL
    sym.mode = GradientMode.SYMMETRIC
    img_sym = _emit(sym)

    lin = GradientSource()
    lin.width = 33
    lin.height = 33
    lin.direction = GradientDirection.RADIAL
    lin.mode = GradientMode.LINEAR
    img_lin = _emit(lin)

    np.testing.assert_array_equal(img_sym, img_lin)


def test_mode_setter_accepts_int_and_enum() -> None:
    node = GradientSource()
    node.mode = 1
    assert node.mode == GradientMode.LINEAR
    node.mode = GradientMode.SYMMETRIC
    assert node.mode == GradientMode.SYMMETRIC


def test_mode_setter_rejects_unknown_value() -> None:
    node = GradientSource()
    with pytest.raises(ValueError):
        node.mode = 99

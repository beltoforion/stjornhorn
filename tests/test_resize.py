"""Unit tests for the Resize transform node."""
from __future__ import annotations

import numpy as np
import pytest

from core.io_data import IoData, IoDataType
from core.port import OutputPort
from nodes.filters.resize import Resize, ResizeMethod


def _bgr(h: int, w: int, value: int = 0) -> np.ndarray:
    return np.full((h, w, 3), value, dtype=np.uint8)


def _grey(h: int, w: int, value: int = 0) -> np.ndarray:
    return np.full((h, w), value, dtype=np.uint8)


def _gradient_bgr(h: int, w: int) -> np.ndarray:
    """An h×w BGR image whose B channel ramps along the row index — gives
    every row a unique value so a centred crop is observable in the
    output without colour artefacts confusing the assertion."""
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[..., 0] = np.arange(h, dtype=np.uint8)[:, None]
    return img


def _drive(node: Resize, image: np.ndarray, *, grey: bool = False) -> IoData:
    up = OutputPort("up", {IoDataType.IMAGE_GREY if grey else IoDataType.IMAGE})
    up.connect(node.inputs[0])
    if grey:
        up.send(IoData.from_greyscale(image))
    else:
        up.send(IoData.from_image(image))
    out = node.outputs[0].last_emitted
    assert out is not None
    return out


# ── Defaults / setters ────────────────────────────────────────────────────────


def test_defaults_match_declared_params() -> None:
    node = Resize()
    assert node.width == 256
    assert node.height == 256
    assert node.method is ResizeMethod.SCALE


def test_width_height_setters_reject_non_positive() -> None:
    node = Resize()
    with pytest.raises(ValueError, match="width must be >= 1"):
        node.width = 0
    with pytest.raises(ValueError, match="height must be >= 1"):
        node.height = -5


def test_method_setter_accepts_int_and_enum() -> None:
    """Flow-load path goes through ``setattr(node, "method", <int>)`` —
    coercion must accept both ints and enum members."""
    node = Resize()
    node.method = 1
    assert node.method is ResizeMethod.CROP_OR_FILL
    node.method = ResizeMethod.BEST_FIT
    assert node.method is ResizeMethod.BEST_FIT


def test_method_setter_rejects_unknown_value() -> None:
    node = Resize()
    # EnumParam phrases this as "method: cannot map 99 to a
    # ResizeMethod member"; the legacy hand-rolled setter said
    # "method must be one of [...]". Either way an out-of-range int
    # raises ValueError at assignment time.
    with pytest.raises(ValueError, match="method"):
        node.method = 99


# ── SCALE ────────────────────────────────────────────────────────────────────


def test_scale_stretches_independently() -> None:
    """SCALE blindly resizes to (width, height) — aspect ratio is not
    preserved, so a 4×4 source forced to 12×6 ends up 6 rows × 12 cols."""
    node = Resize()
    node.method = ResizeMethod.SCALE
    node.width = 12
    node.height = 6

    out = _drive(node, _bgr(4, 4, 200))

    assert out.image.shape == (6, 12, 3)
    # Uniform-coloured source → uniform-coloured output regardless of
    # the stretch factor.
    assert int(out.image[0, 0, 0]) == 200
    assert int(out.image[5, 11, 0]) == 200


def test_scale_preserves_dtype_and_channel_count() -> None:
    node = Resize()
    node.method = ResizeMethod.SCALE
    node.width = 8
    node.height = 8

    out = _drive(node, _bgr(4, 4, 100))
    assert out.image.dtype == np.uint8
    assert out.image.shape == (8, 8, 3)


def test_scale_works_on_greyscale() -> None:
    node = Resize()
    node.method = ResizeMethod.SCALE
    node.width = 6
    node.height = 6

    out = _drive(node, _grey(3, 3, 42), grey=True)

    assert out.type is IoDataType.IMAGE_GREY
    assert out.image.shape == (6, 6)
    assert int(out.image[0, 0]) == 42


# ── CROP_OR_FILL ─────────────────────────────────────────────────────────────


def test_crop_or_fill_smaller_target_centre_crops() -> None:
    """Source larger than target on both axes → centred crop at
    pixel scale, no resampling."""
    node = Resize()
    node.method = ResizeMethod.CROP_OR_FILL
    node.width = 4
    node.height = 4

    src = _gradient_bgr(8, 8)  # B channel rows = 0..7
    out = _drive(node, src)

    assert out.image.shape == (4, 4, 3)
    # Centred crop of an 8×8 source into 4×4 picks rows 2..5 / cols 2..5.
    np.testing.assert_array_equal(out.image, src[2:6, 2:6])


def test_crop_or_fill_larger_target_centres_with_black_margin() -> None:
    """Source smaller than target on both axes → source placed in the
    centre, surrounded by black."""
    node = Resize()
    node.method = ResizeMethod.CROP_OR_FILL
    node.width = 8
    node.height = 8

    src = _bgr(4, 4, 200)
    out = _drive(node, src)

    assert out.image.shape == (8, 8, 3)
    # 4×4 source centred in an 8×8 canvas → rows 2..5, cols 2..5.
    np.testing.assert_array_equal(out.image[2:6, 2:6], _bgr(4, 4, 200))
    # Margins are pure black.
    assert out.image[0:2, :].sum() == 0
    assert out.image[6:, :].sum() == 0
    assert out.image[:, 0:2].sum() == 0
    assert out.image[:, 6:].sum() == 0


def test_crop_or_fill_mixed_axes_crops_one_pads_other() -> None:
    """Source wider but shorter than target → crop the X axis,
    pad the Y axis. Verifies the per-axis centring formula."""
    node = Resize()
    node.method = ResizeMethod.CROP_OR_FILL
    node.width = 4
    node.height = 6

    src = _gradient_bgr(2, 8)  # 2 rows tall, 8 cols wide; B = row index 0..1
    out = _drive(node, src)

    assert out.image.shape == (6, 4, 3)
    # X axis: source 8 → target 4 → crop, src_x0=2, copy 4 cols.
    # Y axis: source 2 → target 6 → pad, dst_y0=2, copy 2 rows.
    np.testing.assert_array_equal(out.image[2:4, 0:4], src[0:2, 2:6])
    # Top and bottom margins on Y are black.
    assert out.image[0:2, :].sum() == 0
    assert out.image[4:6, :].sum() == 0


def test_crop_or_fill_does_not_resample() -> None:
    """CROP_OR_FILL preserves pixel scale — a 1-pixel stripe in the
    source survives byte-for-byte in the output, not blurred."""
    node = Resize()
    node.method = ResizeMethod.CROP_OR_FILL
    node.width = 8
    node.height = 8

    src = np.zeros((4, 4, 3), dtype=np.uint8)
    src[1, 2] = (10, 20, 30)  # single pixel, distinct value
    out = _drive(node, src)

    # Source centre is at (1.5, 1.5); target centre at (3.5, 3.5).
    # The source pixel at (1, 2) lands at (3, 4) on the 8×8 canvas.
    np.testing.assert_array_equal(out.image[3, 4], (10, 20, 30))


# ── BEST_FIT ─────────────────────────────────────────────────────────────────


def test_best_fit_letterboxes_when_target_is_wider() -> None:
    """Source 4:3 aspect (e.g. 4×3) into a 16:6 target → height is the
    limiting axis. Resized source is 8×6, centred horizontally with
    4-pixel pillarbox black margins on each side."""
    node = Resize()
    node.method = ResizeMethod.BEST_FIT
    node.width = 16
    node.height = 6

    src = _bgr(3, 4, 200)
    out = _drive(node, src)

    assert out.image.shape == (6, 16, 3)
    # scale = min(16/4, 6/3) = min(4, 2) = 2 → new size 8 wide × 6 tall.
    # Centred → cols 4..11 are the 200-filled scaled source.
    # Pillarbox: cols 0..3 and 12..15 stay black.
    assert out.image[:, 4:12].min() == 200, "scaled source region should be 200"
    assert out.image[:, 0:4].sum() == 0
    assert out.image[:, 12:16].sum() == 0


def test_best_fit_pillarboxes_when_target_is_taller() -> None:
    """Aspect ratio inverts the previous test — width is now the
    limiting axis, the resized source spans top / bottom and the
    canvas keeps a letterbox top + bottom black margin."""
    node = Resize()
    node.method = ResizeMethod.BEST_FIT
    node.width = 4
    node.height = 12

    src = _bgr(2, 4, 200)  # 4 wide × 2 tall (2:1 aspect)
    out = _drive(node, src)

    assert out.image.shape == (12, 4, 3)
    # scale = min(4/4, 12/2) = 1 → new size 4×2, centred → rows 5..6.
    np.testing.assert_array_equal(out.image[5:7, :], _bgr(2, 4, 200))
    assert out.image[0:5, :].sum() == 0
    assert out.image[7:, :].sum() == 0


def test_best_fit_perfect_aspect_match_fills_canvas() -> None:
    """Source aspect ratio matches target exactly → no margin."""
    node = Resize()
    node.method = ResizeMethod.BEST_FIT
    node.width = 8
    node.height = 8

    out = _drive(node, _bgr(4, 4, 200))

    assert out.image.shape == (8, 8, 3)
    # Whole canvas is 200 (no black margin).
    assert out.image.min() == 200


def test_best_fit_preserves_channel_count_for_bgra() -> None:
    """4-channel BGRA inputs round-trip with their alpha channel
    preserved on the resized region; the canvas margin stays at the
    raw zero-fill (alpha=0 — transparent black)."""
    node = Resize()
    node.method = ResizeMethod.BEST_FIT
    node.width = 8
    node.height = 4

    src = np.zeros((4, 4, 4), dtype=np.uint8)
    src[..., :3] = 200
    src[..., 3] = 255  # opaque
    out = _drive(node, src)

    assert out.image.shape == (4, 8, 4)
    # scale = min(8/4, 4/4) = 1 → new size 4×4; centred → cols 2..5.
    np.testing.assert_array_equal(out.image[:, 2:6, :3], _bgr(4, 4, 200))
    assert (out.image[:, 2:6, 3] == 255).all()
    # Margins keep the raw zero fill (alpha=0).
    assert (out.image[:, 0:2, 3] == 0).all()
    assert (out.image[:, 6:, 3] == 0).all()

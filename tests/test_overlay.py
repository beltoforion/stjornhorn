"""Unit tests for the Overlay (composite with alpha) node."""
from __future__ import annotations

import numpy as np

from core.io_data import IoData, IoDataType
from core.port import OutputPort
from nodes.filters.overlay import Overlay


def _bgr(h: int, w: int, value: int) -> np.ndarray:
    return np.full((h, w, 3), value, dtype=np.uint8)


def _grey(h: int, w: int, value: int) -> np.ndarray:
    return np.full((h, w), value, dtype=np.uint8)


def _wire(node: Overlay, base: IoData, overlay: IoData) -> None:
    """Connect upstreams for both inputs, then push data into each."""
    up_base = OutputPort("base", {base.type})
    up_ov   = OutputPort("overlay", {overlay.type})
    up_base.connect(node.inputs[0])
    up_ov.connect(node.inputs[1])
    up_base.send(base)
    up_ov.send(overlay)


def test_overlay_full_alpha_replaces_pixels_in_roi() -> None:
    node = Overlay()
    node.alpha = 1.0
    node.xpos = 2
    node.ypos = 3
    node.scale = 1.0
    _wire(
        node,
        IoData.from_image(_bgr(10, 10, 50)),
        IoData.from_image(_bgr(4, 5, 200)),
    )

    out = node.outputs[0].last_emitted
    assert out is not None
    assert out.type == IoDataType.IMAGE
    assert out.image.shape == (10, 10, 3)
    # ROI at (y=3..7, x=2..7) is fully replaced by overlay.
    np.testing.assert_array_equal(out.image[3:7, 2:7], _bgr(4, 5, 200))
    # A pixel outside the ROI keeps the base value.
    assert out.image[0, 0, 0] == 50


def test_overlay_zero_alpha_keeps_base() -> None:
    node = Overlay()
    node.alpha = 0.0
    _wire(
        node,
        IoData.from_image(_bgr(6, 6, 80)),
        IoData.from_image(_bgr(3, 3, 255)),
    )

    out = node.outputs[0].last_emitted
    assert out is not None
    np.testing.assert_array_equal(out.image, _bgr(6, 6, 80))


def test_overlay_half_alpha_blends_50_50() -> None:
    node = Overlay()
    node.alpha = 0.5
    node.xpos = 0
    node.ypos = 0
    _wire(
        node,
        IoData.from_image(_bgr(4, 4, 100)),
        IoData.from_image(_bgr(4, 4, 200)),
    )

    out = node.outputs[0].last_emitted
    assert out is not None
    # 0.5*200 + 0.5*100 = 150.
    assert out.image[0, 0, 0] == 150


def test_overlay_scale_resizes_overlay_before_compositing() -> None:
    node = Overlay()
    node.scale = 2.0
    node.alpha = 1.0
    _wire(
        node,
        IoData.from_image(_bgr(10, 10, 0)),
        IoData.from_image(_bgr(2, 2, 255)),
    )

    out = node.outputs[0].last_emitted
    assert out is not None
    # Overlay was 2x2, scale=2 -> 4x4 drawn at (0,0).
    np.testing.assert_array_equal(out.image[0:4, 0:4], _bgr(4, 4, 255))
    # Rest of the canvas untouched.
    assert out.image[5:, 5:].sum() == 0


def test_overlay_clips_when_partially_outside_base() -> None:
    node = Overlay()
    node.alpha = 1.0
    node.xpos = 8
    node.ypos = 8
    _wire(
        node,
        IoData.from_image(_bgr(10, 10, 0)),
        IoData.from_image(_bgr(4, 4, 255)),
    )

    out = node.outputs[0].last_emitted
    assert out is not None
    # Only the 2x2 top-left corner of the overlay lands on the base.
    np.testing.assert_array_equal(out.image[8:10, 8:10], _bgr(2, 2, 255))


def test_overlay_negative_position_clips_top_left() -> None:
    node = Overlay()
    node.alpha = 1.0
    node.xpos = -2
    node.ypos = -3
    _wire(
        node,
        IoData.from_image(_bgr(10, 10, 0)),
        IoData.from_image(_bgr(6, 6, 255)),
    )

    out = node.outputs[0].last_emitted
    assert out is not None
    # Visible chunk: overlay rows 3..6, cols 2..6 land at base (0..3, 0..4).
    np.testing.assert_array_equal(out.image[0:3, 0:4], _bgr(3, 4, 255))


def test_overlay_fully_outside_base_is_noop() -> None:
    node = Overlay()
    node.alpha = 1.0
    node.xpos = 100
    node.ypos = 100
    base = _bgr(10, 10, 42)
    _wire(
        node,
        IoData.from_image(base.copy()),
        IoData.from_image(_bgr(4, 4, 255)),
    )

    out = node.outputs[0].last_emitted
    assert out is not None
    np.testing.assert_array_equal(out.image, base)


def test_overlay_greyscale_base_and_overlay_stays_greyscale() -> None:
    node = Overlay()
    node.alpha = 1.0
    _wire(
        node,
        IoData.from_greyscale(_grey(5, 5, 20)),
        IoData.from_greyscale(_grey(2, 2, 200)),
    )

    out = node.outputs[0].last_emitted
    assert out is not None
    assert out.type == IoDataType.IMAGE_GREY
    assert out.image.shape == (5, 5)
    assert out.image[0, 0] == 200
    assert out.image[4, 4] == 20


def test_overlay_mixed_types_promotes_output_to_color() -> None:
    node = Overlay()
    node.alpha = 1.0
    _wire(
        node,
        IoData.from_image(_bgr(4, 4, 10)),
        IoData.from_greyscale(_grey(2, 2, 99)),
    )

    out = node.outputs[0].last_emitted
    assert out is not None
    assert out.type == IoDataType.IMAGE
    # Greyscale overlay is promoted to BGR, so every channel reads 99.
    np.testing.assert_array_equal(out.image[0:2, 0:2], _bgr(2, 2, 99))


def test_overlay_does_not_mutate_base_input() -> None:
    node = Overlay()
    node.alpha = 1.0
    base_img = _bgr(4, 4, 50)
    _wire(
        node,
        IoData.from_image(base_img),
        IoData.from_image(_bgr(2, 2, 200)),
    )

    # Input image object must be left intact for downstream consumers.
    np.testing.assert_array_equal(base_img, _bgr(4, 4, 50))


def test_overlay_angle_zero_is_no_op() -> None:
    node = Overlay()
    node.alpha = 1.0
    node.angle = 0.0
    _wire(
        node,
        IoData.from_image(_bgr(8, 8, 0)),
        IoData.from_image(_bgr(3, 3, 200)),
    )

    out = node.outputs[0].last_emitted
    assert out is not None
    # With no rotation the overlay is placed as a plain 3x3 block.
    np.testing.assert_array_equal(out.image[0:3, 0:3], _bgr(3, 3, 200))


def test_overlay_angle_90_swaps_bounding_box_dimensions() -> None:
    node = Overlay()
    node.alpha = 1.0
    node.angle = 90.0
    # Non-square overlay so the rotation is observable in the output shape.
    base = _bgr(20, 20, 0)
    overlay = _bgr(2, 6, 255)  # 2 rows, 6 cols
    _wire(node, IoData.from_image(base), IoData.from_image(overlay))

    out = node.outputs[0].last_emitted
    assert out is not None
    # A 90° rotation maps a 2x6 block to a 6x2 footprint on the base —
    # the rotated overlay occupies rows 0..6, cols 0..2 with interpolation
    # artifacts on the outer edges. We only check that *most* of that
    # region is non-black and that pixels fully outside it are still black.
    footprint_nonzero = (out.image[0:6, 0:2] > 0).any(axis=2).sum()
    assert footprint_nonzero >= 10  # out of a 6x2 = 12-pixel region
    # Pixels strictly outside the rotated bounding box stay black.
    assert out.image[0:6, 2:20].sum() == 0
    assert out.image[6:20, 0:20].sum() == 0


def test_overlay_angle_360_matches_angle_zero() -> None:
    node = Overlay()
    node.alpha = 1.0
    node.angle = 360.0
    _wire(
        node,
        IoData.from_image(_bgr(8, 8, 0)),
        IoData.from_image(_bgr(3, 3, 200)),
    )

    out = node.outputs[0].last_emitted
    assert out is not None
    # 360° rotation is treated as identity (skips the warp entirely).
    np.testing.assert_array_equal(out.image[0:3, 0:3], _bgr(3, 3, 200))


def test_overlay_angle_and_scale_combine_into_single_warp() -> None:
    node = Overlay()
    node.alpha = 1.0
    node.angle = 90.0
    node.scale = 2.0
    # 2x3 overlay, rotated 90° and scaled 2x, should land as a 6x4
    # bounding box on the base (height 2*3 = 6 rows, width 2*2 = 4 cols).
    _wire(
        node,
        IoData.from_image(_bgr(20, 20, 0)),
        IoData.from_image(_bgr(2, 3, 255)),
    )

    out = node.outputs[0].last_emitted
    assert out is not None
    # Expected footprint is 6x4 starting at (0, 0); everything outside
    # it must remain black.
    assert out.image[0:6, 4:20].sum() == 0
    assert out.image[6:20, 0:20].sum() == 0
    # Most pixels inside the bounding box are non-black (edge pixels may
    # be partially blended with the BORDER_CONSTANT=0 background).
    footprint_nonzero = (out.image[0:6, 0:4] > 0).any(axis=2).sum()
    assert footprint_nonzero >= 20  # out of 6x4 = 24 pixels


def test_overlay_zero_alpha_skips_warp(monkeypatch) -> None:
    """With alpha=0 the overlay is invisible — warpAffine must not run."""
    import cv2 as _cv2
    calls = {"warp": 0, "resize": 0}
    monkeypatch.setattr(_cv2, "warpAffine",
                        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("warpAffine called")))
    monkeypatch.setattr(_cv2, "resize",
                        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("resize called")))

    node = Overlay()
    node.alpha = 0.0
    node.scale = 2.5
    node.angle = 37.0  # would normally force a warpAffine
    base = _bgr(8, 8, 42)
    _wire(
        node,
        IoData.from_image(base),
        IoData.from_image(_bgr(3, 3, 255)),
    )

    out = node.outputs[0].last_emitted
    assert out is not None
    np.testing.assert_array_equal(out.image, base)


def test_overlay_fully_outside_base_skips_warp(monkeypatch) -> None:
    """Overlay positioned off-canvas must not trigger the warp pipeline."""
    import cv2 as _cv2
    monkeypatch.setattr(_cv2, "warpAffine",
                        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("warpAffine called")))
    monkeypatch.setattr(_cv2, "resize",
                        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("resize called")))

    node = Overlay()
    node.alpha = 1.0
    node.scale = 2.0
    node.angle = 45.0
    node.xpos = 500  # far outside the 10x10 base
    node.ypos = 500
    base = _bgr(10, 10, 99)
    _wire(
        node,
        IoData.from_image(base),
        IoData.from_image(_bgr(4, 4, 255)),
    )

    out = node.outputs[0].last_emitted
    assert out is not None
    np.testing.assert_array_equal(out.image, base)


def test_overlay_defaults_match_declared_params() -> None:
    node = Overlay()
    assert node.scale == 1.0
    assert node.angle == 0.0
    assert node.xpos == 0
    assert node.ypos == 0
    assert node.alpha == 1.0


def test_overlay_alpha_is_clamped_to_unit_interval() -> None:
    node = Overlay()
    node.alpha = 2.5
    assert node.alpha == 1.0
    node.alpha = -0.3
    assert node.alpha == 0.0


def test_overlay_rejects_non_positive_scale() -> None:
    node = Overlay()
    import pytest
    with pytest.raises(ValueError):
        node.scale = 0.0
    with pytest.raises(ValueError):
        node.scale = -1.0

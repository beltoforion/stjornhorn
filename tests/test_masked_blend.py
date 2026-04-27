"""Unit tests for the MaskedBlend node."""
from __future__ import annotations

import numpy as np
import pytest

from core.io_data import IoData, IoDataType
from core.port import OutputPort
from nodes.filters.masked_blend import MaskedBlend


def _bgr(h: int, w: int, value: int) -> np.ndarray:
    return np.full((h, w, 3), value, dtype=np.uint8)


def _grey(h: int, w: int, value: int) -> np.ndarray:
    return np.full((h, w), value, dtype=np.uint8)


def _wire(node: MaskedBlend, base: IoData, overlay: IoData, mask: IoData) -> None:
    up_base = OutputPort("base", {base.type})
    up_ov   = OutputPort("overlay", {overlay.type})
    up_mask = OutputPort("mask", {mask.type})
    up_base.connect(node.inputs[0])
    up_ov.connect(node.inputs[1])
    up_mask.connect(node.inputs[2])
    up_base.send(base)
    up_ov.send(overlay)
    up_mask.send(mask)


def test_black_mask_emits_base_unchanged() -> None:
    node = MaskedBlend()
    _wire(
        node,
        IoData.from_image(_bgr(4, 4, 100)),
        IoData.from_image(_bgr(4, 4, 200)),
        IoData.from_greyscale(_grey(4, 4, 0)),
    )
    out = node.outputs[0].last_emitted
    assert out is not None
    assert out.type == IoDataType.IMAGE
    np.testing.assert_array_equal(out.image, _bgr(4, 4, 100))


def test_white_mask_emits_overlay_unchanged() -> None:
    node = MaskedBlend()
    _wire(
        node,
        IoData.from_image(_bgr(4, 4, 100)),
        IoData.from_image(_bgr(4, 4, 200)),
        IoData.from_greyscale(_grey(4, 4, 255)),
    )
    out = node.outputs[0].last_emitted
    assert out is not None
    np.testing.assert_array_equal(out.image, _bgr(4, 4, 200))


def test_half_mask_blends_50_50() -> None:
    node = MaskedBlend()
    _wire(
        node,
        IoData.from_image(_bgr(4, 4, 100)),
        IoData.from_image(_bgr(4, 4, 200)),
        IoData.from_greyscale(_grey(4, 4, 128)),
    )
    out = node.outputs[0].last_emitted
    assert out is not None
    # m = 128/255 ≈ 0.502; 100*(1-m) + 200*m ≈ 150 (±1 for rounding).
    assert abs(int(out.image[0, 0, 0]) - 150) <= 1


def test_per_pixel_mask_drives_per_pixel_blend() -> None:
    """A mask with row 0 black and row 1 white must produce row 0 = base
    and row 1 = overlay."""
    node = MaskedBlend()
    base = _bgr(2, 2, 50)
    overlay = _bgr(2, 2, 250)
    mask = np.array([[0, 0], [255, 255]], dtype=np.uint8)
    _wire(
        node,
        IoData.from_image(base),
        IoData.from_image(overlay),
        IoData.from_greyscale(mask),
    )
    out = node.outputs[0].last_emitted
    assert out is not None
    np.testing.assert_array_equal(out.image[0], _bgr(1, 2, 50)[0])
    np.testing.assert_array_equal(out.image[1], _bgr(1, 2, 250)[0])


def test_mismatched_base_overlay_raises() -> None:
    node = MaskedBlend()
    with pytest.raises(ValueError, match="base shape"):
        _wire(
            node,
            IoData.from_image(_bgr(4, 4, 0)),
            IoData.from_image(_bgr(4, 5, 0)),
            IoData.from_greyscale(_grey(4, 4, 128)),
        )


def test_mask_resized_to_base_when_shape_differs() -> None:
    """A small mask must be resized to the base's H x W rather than
    triggering a shape error — lets a small procedural gradient drive
    a full-resolution stream."""
    node = MaskedBlend()
    base = _bgr(8, 8, 100)
    overlay = _bgr(8, 8, 200)
    # 4x4 mask, all white — after resize it stays all white.
    mask = _grey(4, 4, 255)
    _wire(
        node,
        IoData.from_image(base),
        IoData.from_image(overlay),
        IoData.from_greyscale(mask),
    )
    out = node.outputs[0].last_emitted
    assert out is not None
    np.testing.assert_array_equal(out.image, _bgr(8, 8, 200))


def test_grey_base_and_overlay_stays_grey() -> None:
    node = MaskedBlend()
    _wire(
        node,
        IoData.from_greyscale(_grey(4, 4, 50)),
        IoData.from_greyscale(_grey(4, 4, 200)),
        IoData.from_greyscale(_grey(4, 4, 0)),
    )
    out = node.outputs[0].last_emitted
    assert out is not None
    assert out.type == IoDataType.IMAGE_GREY
    assert out.image.shape == (4, 4)
    np.testing.assert_array_equal(out.image, _grey(4, 4, 50))


def test_mixed_types_promote_output_to_color() -> None:
    node = MaskedBlend()
    _wire(
        node,
        IoData.from_image(_bgr(4, 4, 0)),
        IoData.from_greyscale(_grey(4, 4, 200)),
        IoData.from_greyscale(_grey(4, 4, 255)),
    )
    out = node.outputs[0].last_emitted
    assert out is not None
    assert out.type == IoDataType.IMAGE
    # Greyscale overlay 200 promoted to BGR (200, 200, 200).
    np.testing.assert_array_equal(out.image, _bgr(4, 4, 200))


def test_color_mask_uses_first_channel() -> None:
    """ImageSource emits a BGR-promoted greyscale gradient as 3-channel
    IMAGE. MaskedBlend reduces it to a single plane internally."""
    node = MaskedBlend()
    base = _bgr(4, 4, 0)
    overlay = _bgr(4, 4, 255)
    # 3-channel "mask" with B=255 in column 0, B=0 elsewhere — the
    # first-channel reduction makes column 0 fully blend in the overlay.
    mask = np.zeros((4, 4, 3), dtype=np.uint8)
    mask[:, 0, 0] = 255
    _wire(
        node,
        IoData.from_image(base),
        IoData.from_image(overlay),
        IoData.from_image(mask),
    )
    out = node.outputs[0].last_emitted
    assert out is not None
    np.testing.assert_array_equal(out.image[:, 0], _bgr(1, 4, 255)[0])
    np.testing.assert_array_equal(out.image[:, 1:], _bgr(4, 3, 0))


def test_bgra_base_alpha_is_dropped() -> None:
    """An RGBA PNG fed into base must blend correctly without crashing
    on the 4th channel — the alpha plane is stripped before the math."""
    node = MaskedBlend()
    base = np.zeros((4, 4, 4), dtype=np.uint8)
    base[..., :3] = 100
    base[..., 3] = 0  # would corrupt the math if not stripped
    overlay = _bgr(4, 4, 200)
    mask = _grey(4, 4, 255)
    _wire(
        node,
        IoData.from_image(base),
        IoData.from_image(overlay),
        IoData.from_greyscale(mask),
    )
    out = node.outputs[0].last_emitted
    assert out is not None
    assert out.image.shape == (4, 4, 3)
    np.testing.assert_array_equal(out.image, _bgr(4, 4, 200))


def test_does_not_mutate_inputs() -> None:
    node = MaskedBlend()
    base = _bgr(4, 4, 50)
    overlay = _bgr(4, 4, 200)
    mask = _grey(4, 4, 128)
    _wire(
        node,
        IoData.from_image(base),
        IoData.from_image(overlay),
        IoData.from_greyscale(mask),
    )
    np.testing.assert_array_equal(base, _bgr(4, 4, 50))
    np.testing.assert_array_equal(overlay, _bgr(4, 4, 200))
    np.testing.assert_array_equal(mask, _grey(4, 4, 128))

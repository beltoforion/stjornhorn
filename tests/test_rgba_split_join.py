"""Unit tests for the RGBA-aware split / join filters."""
from __future__ import annotations

import numpy as np

from core.io_data import IoData, IoDataType
from core.port import InputPort, OutputPort
from nodes.filters.rgba_join import RgbaJoin
from nodes.filters.rgba_split import RgbaSplit


# ── RgbaSplit ──────────────────────────────────────────────────────────────────

def test_rgba_split_on_bgr_emits_full_opaque_alpha() -> None:
    """A 3-channel BGR image must still produce 4 output planes, with the
    synthesised alpha plane being full-opaque (255) everywhere."""
    node = RgbaSplit()
    image = np.dstack([
        np.full((3, 4), 10, dtype=np.uint8),   # B
        np.full((3, 4), 20, dtype=np.uint8),   # G
        np.full((3, 4), 30, dtype=np.uint8),   # R
    ])
    node.inputs[0].receive(IoData.from_image(image))

    b, g, r, a = (p.last_emitted for p in node.outputs)
    assert a is not None and a.type == IoDataType.IMAGE_GREY
    np.testing.assert_array_equal(b.image, 10)
    np.testing.assert_array_equal(g.image, 20)
    np.testing.assert_array_equal(r.image, 30)
    np.testing.assert_array_equal(a.image, 255)


def test_rgba_split_on_bgra_preserves_alpha_channel() -> None:
    """A 4-channel BGRA image must propagate the alpha plane verbatim."""
    node = RgbaSplit()
    image = np.dstack([
        np.full((2, 2), 1, dtype=np.uint8),
        np.full((2, 2), 2, dtype=np.uint8),
        np.full((2, 2), 3, dtype=np.uint8),
        np.array([[0, 128], [64, 255]], dtype=np.uint8),
    ])
    node.inputs[0].receive(IoData.from_image(image))

    b, g, r, a = (p.last_emitted for p in node.outputs)
    np.testing.assert_array_equal(b.image, 1)
    np.testing.assert_array_equal(g.image, 2)
    np.testing.assert_array_equal(r.image, 3)
    np.testing.assert_array_equal(a.image, np.array([[0, 128], [64, 255]], dtype=np.uint8))


# ── RgbaJoin ───────────────────────────────────────────────────────────────────

def _grey(value: int) -> IoData:
    return IoData.from_greyscale(np.full((2, 2), value, dtype=np.uint8))


def _wire_bgr(node: RgbaJoin) -> None:
    """Push B, G, R via direct ``receive`` calls (no upstream needed for
    required ports — they always fire once all three arrive)."""
    node.inputs[0].receive(_grey(10))  # B
    node.inputs[1].receive(_grey(20))  # G
    node.inputs[2].receive(_grey(30))  # R


def test_rgba_join_without_alpha_emits_bgr() -> None:
    """Only B/G/R connected — the A port is optional and has no upstream,
    so the dispatcher fires on the three required inputs alone and the
    node emits a plain 3-channel BGR image."""
    node = RgbaJoin()
    _wire_bgr(node)

    out = node.outputs[0].last_emitted
    assert out is not None and out.type == IoDataType.IMAGE
    assert out.image.shape == (2, 2, 3)
    np.testing.assert_array_equal(out.image[..., 0], 10)
    np.testing.assert_array_equal(out.image[..., 1], 20)
    np.testing.assert_array_equal(out.image[..., 2], 30)


def test_rgba_join_with_alpha_emits_bgra() -> None:
    """All four inputs connected — output is a 4-channel BGRA image.

    The A port must have an upstream wired before any required input
    pushes data; otherwise the dispatcher would fire on B/G/R alone and
    drop the alpha frame. This mirrors how RgbaSplit → RgbaJoin actually
    connects in a flow.
    """
    node = RgbaJoin()
    up_alpha = OutputPort("a", {IoDataType.IMAGE_GREY})
    up_alpha.connect(node.inputs[3])
    _wire_bgr(node)
    up_alpha.send(_grey(128))

    out = node.outputs[0].last_emitted
    assert out is not None and out.type == IoDataType.IMAGE
    assert out.image.shape == (2, 2, 4)
    np.testing.assert_array_equal(out.image[..., 3], 128)


def test_rgba_join_alpha_input_is_marked_optional() -> None:
    """The A port must carry ``optional=True`` so the dispatcher does not
    block when it is left dangling."""
    node = RgbaJoin()
    assert node.inputs[0].optional is False
    assert node.inputs[1].optional is False
    assert node.inputs[2].optional is False
    assert node.inputs[3].optional is True


# ── Round-trip ──────────────────────────────────────────────────────────────────

def test_split_join_roundtrip_on_bgra_is_identity() -> None:
    """Splitting a BGRA image and rejoining it must reproduce the original."""
    split = RgbaSplit()
    join  = RgbaJoin()
    for i in range(4):
        split.outputs[i].connect(join.inputs[i])

    # Also wire a capture port so we can assert on the join's output.
    capture = InputPort("cap", {IoDataType.IMAGE})
    join.outputs[0].connect(capture)

    original = np.dstack([
        np.arange(8, dtype=np.uint8).reshape(2, 4) * 10,
        np.arange(8, dtype=np.uint8).reshape(2, 4) * 20,
        np.arange(8, dtype=np.uint8).reshape(2, 4) * 30,
        np.arange(8, dtype=np.uint8).reshape(2, 4) * 32,
    ])
    split.inputs[0].receive(IoData.from_image(original))

    assert capture.has_data
    np.testing.assert_array_equal(capture.data.image, original)

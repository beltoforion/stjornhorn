"""Unit tests for the ApplyColormap filter."""
from __future__ import annotations

import cv2
import numpy as np
import pytest

from core.io_data import IoData, IoDataType
from nodes.filters.apply_colormap import ApplyColormap, Colormap


def _ramp(h: int = 8, w: int = 256) -> np.ndarray:
    """Deterministic 0..255 horizontal ramp; exercises the full LUT."""
    row = (np.arange(w) % 256).astype(np.uint8)
    return np.tile(row, (h, 1))


def test_emits_bgr_image_with_same_spatial_shape() -> None:
    node = ApplyColormap()
    grey = _ramp(8, 16)
    node.inputs[0].receive(IoData.from_greyscale(grey))

    out = node.outputs[0].last_emitted
    assert out is not None
    assert out.type == IoDataType.IMAGE
    assert out.image.shape == (8, 16, 3)
    assert out.image.dtype == np.uint8


def test_default_colormap_is_viridis() -> None:
    node = ApplyColormap()
    assert node.colormap == Colormap.VIRIDIS


def test_output_matches_cv2_apply_colormap_directly() -> None:
    """The node must be a thin wrapper — output must equal cv2.applyColorMap."""
    node = ApplyColormap()
    node.colormap = Colormap.JET
    grey = _ramp()

    node.inputs[0].receive(IoData.from_greyscale(grey))
    out = node.outputs[0].last_emitted.image

    expected = cv2.applyColorMap(grey, cv2.COLORMAP_JET)
    np.testing.assert_array_equal(out, expected)


@pytest.mark.parametrize("cmap", list(Colormap))
def test_every_colormap_produces_valid_bgr(cmap: Colormap) -> None:
    """Every enum member must round-trip through cv2.applyColorMap cleanly.

    Guards against an enum value that doesn't correspond to a real
    ``cv2.COLORMAP_*`` constant on the installed OpenCV.
    """
    node = ApplyColormap()
    node.colormap = cmap
    grey = _ramp(4, 32)

    node.inputs[0].receive(IoData.from_greyscale(grey))
    out = node.outputs[0].last_emitted
    assert out is not None
    assert out.image.shape == (4, 32, 3)
    assert out.image.dtype == np.uint8


def test_colormap_setter_accepts_int_values() -> None:
    """Saved flows persist enums as ints; the setter must coerce back."""
    node = ApplyColormap()
    node.colormap = int(Colormap.MAGMA)
    assert node.colormap == Colormap.MAGMA


def test_colormap_setter_rejects_unknown_value() -> None:
    node = ApplyColormap()
    # EnumParam phrases this as "colormap: cannot map 9999 to a
    # Colormap member"; the legacy hand-rolled setter said "colormap
    # must be one of [...]". Either way an unknown int raises
    # ValueError at assignment time.
    with pytest.raises(ValueError, match="colormap"):
        node.colormap = 9999


def test_rejects_three_channel_input_at_process_time() -> None:
    """Colour input has no defined mapping; the node must refuse it."""
    node = ApplyColormap()
    bgr = np.zeros((4, 4, 3), dtype=np.uint8)
    try:
        node.inputs[0].receive(IoData.from_greyscale(bgr))
    except Exception as exc:
        assert "single-channel" in str(exc)
    else:
        raise AssertionError("ApplyColormap must reject 3-D input")


def test_non_uint8_input_is_coerced() -> None:
    """Float greyscale (e.g. from a normalized field) should still colorize."""
    node = ApplyColormap()
    grey = np.linspace(0, 255, 64, dtype=np.float32).reshape(8, 8)
    node.inputs[0].receive(IoData.from_greyscale(grey))

    out = node.outputs[0].last_emitted
    assert out is not None
    assert out.image.shape == (8, 8, 3)
    assert out.image.dtype == np.uint8

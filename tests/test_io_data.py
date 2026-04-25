"""Unit tests for the IoData envelope and its payload kinds."""
from __future__ import annotations

import numpy as np
import pytest

from core.io_data import IMAGE_TYPES, IoData, IoDataType


# ── Image / greyscale (existing behaviour, locked-in) ─────────────────────────

def test_from_image_round_trips_payload() -> None:
    img = np.zeros((4, 4, 3), dtype=np.uint8)
    data = IoData.from_image(img)
    assert data.type is IoDataType.IMAGE
    assert data.payload is img
    assert data.image is img  # back-compat alias still works
    assert data.is_image() is True


def test_from_greyscale_round_trips_payload() -> None:
    img = np.zeros((4, 4), dtype=np.uint8)
    data = IoData.from_greyscale(img)
    assert data.type is IoDataType.IMAGE_GREY
    assert data.payload is img
    assert data.is_image() is True


def test_image_types_set_contains_only_image_kinds() -> None:
    assert IMAGE_TYPES == frozenset({IoDataType.IMAGE, IoDataType.IMAGE_GREY})
    assert IoDataType.SCALAR not in IMAGE_TYPES
    assert IoDataType.MATRIX not in IMAGE_TYPES


# ── Scalar payload ────────────────────────────────────────────────────────────

def test_from_scalar_accepts_python_int() -> None:
    data = IoData.from_scalar(42)
    assert data.type is IoDataType.SCALAR
    assert data.payload.ndim == 0
    assert data.payload.item() == 42
    assert data.is_image() is False


def test_from_scalar_accepts_python_float() -> None:
    data = IoData.from_scalar(3.14)
    assert data.type is IoDataType.SCALAR
    assert data.payload.ndim == 0
    assert data.payload.item() == pytest.approx(3.14)


def test_from_scalar_accepts_numpy_scalar() -> None:
    data = IoData.from_scalar(np.int64(7))
    assert data.payload.ndim == 0
    assert data.payload.item() == 7


def test_from_scalar_accepts_zero_d_array() -> None:
    arr = np.array(99)
    data = IoData.from_scalar(arr)
    assert data.payload.ndim == 0
    assert data.payload.item() == 99


def test_from_scalar_rejects_one_d_array() -> None:
    with pytest.raises(ValueError, match="0-d"):
        IoData.from_scalar(np.array([1, 2, 3]))


def test_from_scalar_rejects_two_d_array() -> None:
    with pytest.raises(ValueError, match="0-d"):
        IoData.from_scalar(np.array([[1]]))


# ── Matrix payload ────────────────────────────────────────────────────────────

def test_from_matrix_accepts_two_d_array() -> None:
    m = np.array([[1.0, 2.0], [3.0, 4.0]])
    data = IoData.from_matrix(m)
    assert data.type is IoDataType.MATRIX
    assert data.payload is m
    assert data.payload.shape == (2, 2)
    assert data.is_image() is False


def test_from_matrix_accepts_one_by_one() -> None:
    """A 1×1 matrix is a degenerate but valid case (the user's
    'integer-as-1×1-matrix' example, kept reachable via reshape)."""
    data = IoData.from_matrix(np.array([[42]]))
    assert data.type is IoDataType.MATRIX
    assert data.payload.shape == (1, 1)
    assert data.payload[0, 0] == 42


def test_from_matrix_coerces_nested_list() -> None:
    data = IoData.from_matrix([[1, 2], [3, 4]])
    assert data.payload.shape == (2, 2)


def test_from_matrix_rejects_one_d_array() -> None:
    with pytest.raises(ValueError, match="2-d"):
        IoData.from_matrix(np.array([1, 2, 3]))


def test_from_matrix_rejects_three_d_array() -> None:
    with pytest.raises(ValueError, match="2-d"):
        IoData.from_matrix(np.zeros((2, 2, 2)))


def test_from_matrix_rejects_scalar() -> None:
    with pytest.raises(ValueError, match="2-d"):
        IoData.from_matrix(np.array(7))


# ── repr / metadata ───────────────────────────────────────────────────────────

def test_repr_includes_type_and_shape_for_scalar() -> None:
    r = repr(IoData.from_scalar(5))
    assert "SCALAR" in r
    assert "shape=()" in r


def test_repr_includes_type_and_shape_for_matrix() -> None:
    r = repr(IoData.from_matrix([[1, 2, 3], [4, 5, 6]]))
    assert "MATRIX" in r
    assert "(2, 3)" in r

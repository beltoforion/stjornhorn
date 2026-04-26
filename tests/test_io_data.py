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


# ── BOOL / STRING / ENUM / PATH (param-as-port payload kinds) ─────────────────

from enum import IntEnum
from pathlib import Path


def test_from_bool_true() -> None:
    data = IoData.from_bool(True)
    assert data.type is IoDataType.BOOL
    assert data.payload is True
    assert data.is_image() is False


def test_from_bool_coerces_truthy_value() -> None:
    """``bool(value)`` semantics: any non-zero / non-empty value
    becomes True. Useful when a widget hands the factory a 0/1 int."""
    assert IoData.from_bool(1).payload is True
    assert IoData.from_bool(0).payload is False
    assert IoData.from_bool("anything").payload is True
    assert IoData.from_bool("").payload is False


def test_from_string() -> None:
    data = IoData.from_string("hello")
    assert data.type is IoDataType.STRING
    assert data.payload == "hello"


def test_from_string_coerces_non_string() -> None:
    """Numeric / Path inputs round-trip through ``str(value)`` so a
    saved-flow loader can hand the factory a JSON-loaded value of any
    primitive type without pre-converting."""
    assert IoData.from_string(42).payload == "42"
    assert IoData.from_string(Path("a/b")).payload == str(Path("a/b"))


class _OpEnum(IntEnum):
    ADD = 0
    MUL = 1


def test_from_enum_preserves_member() -> None:
    data = IoData.from_enum(_OpEnum.MUL)
    assert data.type is IoDataType.ENUM
    assert data.payload is _OpEnum.MUL


def test_from_enum_accepts_int_for_round_trip() -> None:
    """A saved flow stores the int value of an IntEnum; round-tripping
    must not crash. Receivers coerce via ``MyEnum(data.payload)``."""
    data = IoData.from_enum(1)
    assert data.payload == 1
    assert _OpEnum(data.payload) is _OpEnum.MUL


def test_from_path_coerces_string() -> None:
    data = IoData.from_path("input/example.jpg")
    assert data.type is IoDataType.PATH
    assert isinstance(data.payload, Path)
    assert str(data.payload) == "input/example.jpg"


def test_from_path_passes_existing_path() -> None:
    p = Path("a/b/c")
    data = IoData.from_path(p)
    assert data.payload == p


def test_repr_for_non_numeric_payloads_uses_value_form() -> None:
    """Non-numeric payloads have no ``shape`` attribute — repr falls
    back to ``value=...`` so the discriminator stays informative."""
    assert "value=True" in repr(IoData.from_bool(True))
    assert "value='hi'" in repr(IoData.from_string("hi"))


def test_image_types_set_unaffected_by_new_kinds() -> None:
    """``IMAGE_TYPES`` must keep being just IMAGE + IMAGE_GREY — adding
    BOOL/STRING/ENUM/PATH must not pollute the set that filters use to
    declare image-only ports."""
    new_kinds = {IoDataType.BOOL, IoDataType.STRING, IoDataType.ENUM, IoDataType.PATH}
    assert IMAGE_TYPES.isdisjoint(new_kinds)

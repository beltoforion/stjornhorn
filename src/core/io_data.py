from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np


class IoDataType(Enum):
    IMAGE = "Image"
    IMAGE_GREY = "ImageGrey"
    SCALAR = "Scalar"
    MATRIX = "Matrix"
    BOOL = "Bool"
    STRING = "String"
    ENUM = "Enum"
    PATH = "Path"


#: Set of :class:`IoDataType` values that carry image payloads. Useful for
#: declaring input/output ports that accept colour or greyscale images
#: interchangeably, e.g. filters like Median and Scale that work on either.
IMAGE_TYPES: frozenset[IoDataType] = frozenset({IoDataType.IMAGE, IoDataType.IMAGE_GREY})


class IoData:
    """Envelope that carries a single payload between nodes in a flow.

    All ports exchange :class:`IoData` objects. The :attr:`type` field acts
    as a discriminator so receiving nodes can decide how to handle the
    payload without inspecting the payload itself.

    Payload kinds:
      - :data:`IoDataType.IMAGE` / :data:`IoDataType.IMAGE_GREY` — 2-D or
        3-D ``uint8`` arrays.
      - :data:`IoDataType.SCALAR` — a numpy 0-d array (``ndim == 0``)
        carrying a single int/float. Use ``.payload.item()`` to read it
        as a Python scalar.
      - :data:`IoDataType.MATRIX` — a 2-D numpy array of arbitrary dtype
        and shape; treats a single value as a 1×1 matrix.
      - :data:`IoDataType.BOOL` / :data:`IoDataType.STRING` /
        :data:`IoDataType.ENUM` / :data:`IoDataType.PATH` — non-numeric
        payloads stored as raw Python objects (``bool``, ``str``,
        ``IntEnum`` / ``int``, ``pathlib.Path``). They exist so that
        every editable property on a node can be modelled as an
        :class:`~core.port.InputPort` (Blender-style); most flows
        won't ever route data into them, the literal default value
        on the port carries the configured value instead.

    Stream lifetime — the signal that a producer is done — is expressed
    out of band via :meth:`core.port.OutputPort.finish`, not through a
    payload value on this channel.
    """

    def __init__(self, type: IoDataType, payload: Any) -> None:
        self._type = type
        self._payload = payload

    # ── Factory methods ────────────────────────────────────────────────────────

    @classmethod
    def from_image(cls, image: np.ndarray) -> IoData:
        """Wrap a (potentially multi-channel) image as :data:`IoDataType.IMAGE`."""
        return cls(IoDataType.IMAGE, payload=image)

    @classmethod
    def from_greyscale(cls, image: np.ndarray) -> IoData:
        """Wrap a single-channel image as :data:`IoDataType.IMAGE_GREY`.

        The image is expected to be a 2-D ``uint8`` array. No shape check is
        enforced — callers are responsible for producing the right shape.
        """
        return cls(IoDataType.IMAGE_GREY, payload=image)

    @classmethod
    def from_scalar(cls, value: object) -> IoData:
        """Wrap a numeric scalar as :data:`IoDataType.SCALAR`.

        Accepts a Python ``int``/``float``, a numpy scalar, or any 0-d
        array. The payload is stored as a 0-d :class:`numpy.ndarray` so
        downstream consumers can treat scalars and matrices uniformly
        through numpy's array API.
        """
        arr = np.asarray(value)
        if arr.ndim != 0:
            raise ValueError(
                f"Scalar payload must be 0-d (ndim==0), got shape {arr.shape}"
            )
        return cls(IoDataType.SCALAR, payload=arr)

    @classmethod
    def from_matrix(cls, matrix: np.ndarray) -> IoData:
        """Wrap a 2-D numpy array as :data:`IoDataType.MATRIX`.

        Accepts any array-like (incl. nested lists); the result is
        coerced to ``np.asarray``. A single value becomes a 1×1 matrix
        if reshaped explicitly by the caller — this factory rejects 0-d
        and 1-d inputs to keep the matrix contract explicit.
        """
        arr = np.asarray(matrix)
        if arr.ndim != 2:
            raise ValueError(
                f"Matrix payload must be 2-d (ndim==2), got shape {arr.shape}"
            )
        return cls(IoDataType.MATRIX, payload=arr)

    @classmethod
    def from_bool(cls, value: object) -> IoData:
        """Wrap a boolean as :data:`IoDataType.BOOL`.

        Coerces with ``bool(value)`` so widget-side strings like
        ``"true"`` / ``"false"`` round-trip predictably (note: Python's
        ``bool("false")`` is ``True`` — callers handing in strings
        should normalise first).
        """
        return cls(IoDataType.BOOL, payload=bool(value))

    @classmethod
    def from_string(cls, value: object) -> IoData:
        """Wrap a string as :data:`IoDataType.STRING`."""
        return cls(IoDataType.STRING, payload=str(value))

    @classmethod
    def from_enum(cls, value: object) -> IoData:
        """Wrap an enum member (or its int value) as :data:`IoDataType.ENUM`.

        The payload is stored verbatim — receivers that expect a
        specific :class:`enum.IntEnum` should coerce on read
        (``MyEnum(data.payload)``) so an ``int`` from a saved flow file
        round-trips through the same path as a typed enum member.
        """
        return cls(IoDataType.ENUM, payload=value)

    @classmethod
    def from_path(cls, value: object) -> IoData:
        """Wrap a filesystem path as :data:`IoDataType.PATH`.

        Coerces to :class:`pathlib.Path` so consumers can rely on the
        ``Path`` API regardless of whether the caller supplied a
        ``str``, an existing ``Path``, or a path-like object.
        """
        return cls(IoDataType.PATH, payload=Path(value))

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def type(self) -> IoDataType:
        return self._type

    @property
    def payload(self) -> Any:
        """The underlying value, regardless of payload kind.

        For image / SCALAR / MATRIX payloads this is a numpy array; for
        BOOL / STRING / ENUM / PATH payloads it is the raw Python
        object. Use :attr:`image` for image-specific code paths that
        expect ``np.ndarray`` semantics.
        """
        return self._payload

    @property
    def image(self) -> np.ndarray:
        """The payload, viewed as an image array.

        Kept for the many image-handling call sites that pre-date the
        SCALAR/MATRIX types. New code that may also handle non-image
        payloads should prefer :attr:`payload`.
        """
        return self._payload

    def is_image(self) -> bool:
        """Return True if this carries an image payload (colour or greyscale)."""
        return self._type in IMAGE_TYPES

    def with_image(self, image: np.ndarray) -> IoData:
        """Return a new :class:`IoData` with the same type and a new payload.

        Use this in pass-through filters so the output type (IMAGE vs
        IMAGE_GREY) matches the input without the filter having to branch on
        it explicitly.
        """
        return IoData(self._type, payload=image)

    def __repr__(self) -> str:
        # Image / SCALAR / MATRIX payloads expose a numpy ``shape``; the
        # non-numeric kinds don't, so fall back to ``repr(value)`` so the
        # __repr__ is meaningful for every payload kind.
        if hasattr(self._payload, "shape"):
            return f"IoData({self._type.name}, shape={self._payload.shape})"
        return f"IoData({self._type.name}, value={self._payload!r})"

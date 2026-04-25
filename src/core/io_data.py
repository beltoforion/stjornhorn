from __future__ import annotations

from enum import Enum

import numpy as np


class IoDataType(Enum):
    IMAGE = "Image"
    IMAGE_GREY = "ImageGrey"
    SCALAR = "Scalar"
    MATRIX = "Matrix"


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

    Stream lifetime — the signal that a producer is done — is expressed
    out of band via :meth:`core.port.OutputPort.finish`, not through a
    payload value on this channel.
    """

    def __init__(self, type: IoDataType, payload: np.ndarray) -> None:
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

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def type(self) -> IoDataType:
        return self._type

    @property
    def payload(self) -> np.ndarray:
        """The underlying numpy array, regardless of payload kind.

        Use this in code that handles SCALAR/MATRIX as well as image
        payloads. Image-specific code can keep using :attr:`image`.
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
        shape = self._payload.shape
        return f"IoData({self._type.name}, shape={shape})"

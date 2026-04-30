from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
from pathlib import Path
from typing import Any, Iterator

import numpy as np
import pandas as pd


class IoDataType(Enum):
    IMAGE = "Image"
    IMAGE_GREY = "ImageGrey"
    SCALAR = "Scalar"
    MATRIX = "Matrix"
    DATASET = "Dataset"
    BOOL = "Bool"
    STRING = "String"
    ENUM = "Enum"
    PATH = "Path"


#: Set of :class:`IoDataType` values that carry image payloads. Useful for
#: declaring input/output ports that accept colour or greyscale images
#: interchangeably, e.g. filters like Median and Scale that work on either.
IMAGE_TYPES: frozenset[IoDataType] = frozenset({IoDataType.IMAGE, IoDataType.IMAGE_GREY})


#: Sentinel for "argument not supplied" on :meth:`IoData.clone`. Lets
#: callers pass ``payload=None`` to actually mean "set the payload to
#: None" rather than colliding with the default.
_UNSET: Any = object()


class IoMeta(Mapping[str, Any]):
    """Open-ended per-frame metadata bag travelling with an :class:`IoData`.

    A free-form ``str → Any`` mapping with **no fixed schema** — any node
    may stamp any key. The framework follows a few conventions so
    different nodes recognise each other's stamps:

    ============  ====================================================
    Key           Stamped by
    ============  ====================================================
    frame_index   :meth:`core.port.OutputPort.send` (per-port counter)
    source_path   source nodes that read from disk (ImageSource,
                  CsvSource), set to the resolved absolute path
    timestamp     run start time, when populated by the runner
    ============  ====================================================

    Custom nodes are free to add domain-specific keys (e.g. a
    ``station`` tag, a ``window_index``); downstream consumers
    decide whether to read them.

    Instances are read-only views over a backing dict — write a new
    copy via :meth:`replace`. Keys are accessed with subscript:

    >>> meta = IoMeta(source_path=Path("a.jpg"), frame_index=3)
    >>> meta["source_path"]
    PosixPath('a.jpg')
    >>> meta.get("missing")  # None — no schema enforces presence
    """

    __slots__ = ("_data",)

    def __init__(
        self,
        _initial: Mapping[str, Any] | None = None,
        /,
        **kwargs: Any,
    ) -> None:
        merged: dict[str, Any] = dict(_initial) if _initial is not None else {}
        merged.update(kwargs)
        # Stored as a plain dict — Mapping API is read-only by absence of
        # __setitem__ on this class. .replace() returns a new IoMeta so
        # callers never mutate shared state.
        object.__setattr__(self, "_data", merged)

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __contains__(self, key: object) -> bool:
        return key in self._data

    def replace(self, **changes: Any) -> "IoMeta":
        """Return a new :class:`IoMeta` with selected keys overridden / added.

        The original is left untouched; the new bag is the union of
        ``self`` and ``changes``, with ``changes`` winning on conflicts.
        """
        merged = dict(self._data)
        merged.update(changes)
        return IoMeta(merged)

    def __repr__(self) -> str:
        return f"IoMeta({self._data!r})"


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
      - :data:`IoDataType.DATASET` — a :class:`pandas.DataFrame` carrying
        labeled tabular data (seismic traces, CV curves, diode I-V,
        spectra, …). Column names identify channels; ``df.attrs`` carries
        free-form metadata (sample rate, units, station, sweep direction,
        …). One generic payload kind serves every domain so the same
        nodes (``Trim``, ``Resample``, ``PlotXY``, …) compose across them.
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

    def __init__(
        self,
        type: IoDataType,
        payload: Any,
        meta: IoMeta | None = None,
    ) -> None:
        self._type = type
        self._payload = payload
        self._meta: IoMeta = meta if meta is not None else IoMeta()

    # ── Factory methods ────────────────────────────────────────────────────────

    @classmethod
    def from_image(cls, image: np.ndarray, *, meta: IoMeta | None = None) -> IoData:
        """Wrap a (potentially multi-channel) image as :data:`IoDataType.IMAGE`."""
        return cls(IoDataType.IMAGE, payload=image, meta=meta)

    @classmethod
    def from_greyscale(cls, image: np.ndarray, *, meta: IoMeta | None = None) -> IoData:
        """Wrap a single-channel image as :data:`IoDataType.IMAGE_GREY`.

        The image is expected to be a 2-D ``uint8`` array. No shape check is
        enforced — callers are responsible for producing the right shape.
        """
        return cls(IoDataType.IMAGE_GREY, payload=image, meta=meta)

    @classmethod
    def from_scalar(cls, value: object, *, meta: IoMeta | None = None) -> IoData:
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
        return cls(IoDataType.SCALAR, payload=arr, meta=meta)

    @classmethod
    def from_matrix(cls, matrix: np.ndarray, *, meta: IoMeta | None = None) -> IoData:
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
        return cls(IoDataType.MATRIX, payload=arr, meta=meta)

    @classmethod
    def from_dataset(cls, df: pd.DataFrame, *, meta: IoMeta | None = None) -> IoData:
        """Wrap a :class:`pandas.DataFrame` as :data:`IoDataType.DATASET`.

        The DataFrame is stored verbatim — its columns identify channels
        and ``df.attrs`` carries domain metadata (``sample_rate``,
        ``units``, ``station``, ``sweep_dir``, …) that downstream nodes
        consume. Stored by reference, so a producer that mutates the
        DataFrame after sending will be visible to consumers; producers
        that need isolation should ``df.copy()`` before wrapping.

        Rejects non-DataFrame inputs to keep the contract explicit; a
        consumer's ``data.payload`` is always a DataFrame.
        """
        if not isinstance(df, pd.DataFrame):
            raise TypeError(
                f"Dataset payload must be a pandas.DataFrame, "
                f"got {type(df).__name__}"
            )
        return cls(IoDataType.DATASET, payload=df, meta=meta)

    @classmethod
    def from_bool(cls, value: object, *, meta: IoMeta | None = None) -> IoData:
        """Wrap a boolean as :data:`IoDataType.BOOL`.

        Coerces with ``bool(value)`` so widget-side strings like
        ``"true"`` / ``"false"`` round-trip predictably (note: Python's
        ``bool("false")`` is ``True`` — callers handing in strings
        should normalise first).
        """
        return cls(IoDataType.BOOL, payload=bool(value), meta=meta)

    @classmethod
    def from_string(cls, value: object, *, meta: IoMeta | None = None) -> IoData:
        """Wrap a string as :data:`IoDataType.STRING`."""
        return cls(IoDataType.STRING, payload=str(value), meta=meta)

    @classmethod
    def from_enum(cls, value: object, *, meta: IoMeta | None = None) -> IoData:
        """Wrap an enum member (or its int value) as :data:`IoDataType.ENUM`.

        The payload is stored verbatim — receivers that expect a
        specific :class:`enum.IntEnum` should coerce on read
        (``MyEnum(data.payload)``) so an ``int`` from a saved flow file
        round-trips through the same path as a typed enum member.
        """
        return cls(IoDataType.ENUM, payload=value, meta=meta)

    @classmethod
    def from_path(cls, value: object, *, meta: IoMeta | None = None) -> IoData:
        """Wrap a filesystem path as :data:`IoDataType.PATH`.

        Coerces to :class:`pathlib.Path` so consumers can rely on the
        ``Path`` API regardless of whether the caller supplied a
        ``str``, an existing ``Path``, or a path-like object.
        """
        return cls(IoDataType.PATH, payload=Path(value), meta=meta)

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

    @property
    def meta(self) -> IoMeta:
        """Per-frame metadata travelling with the payload."""
        return self._meta

    def is_image(self) -> bool:
        """Return True if this carries an image payload (colour or greyscale)."""
        return self._type in IMAGE_TYPES

    def clone(self, *, payload: Any = _UNSET, **meta_changes: Any) -> IoData:
        """Return a copy of this :class:`IoData` with selected fields replaced.

        Type is always forwarded so a pass-through filter doesn't have
        to branch on IMAGE vs IMAGE_GREY (vs SCALAR vs DATASET).

        - ``payload=value`` overrides the payload verbatim. Pass-through
          filters use this to ship a transformed array without
          rebuilding the envelope.
        - Any other keyword arguments are interpreted as
          :class:`IoMeta` updates and merged via
          :meth:`IoMeta.replace` — ``data.clone(frame_index=5)`` keeps
          the payload, stamps a new index, leaves other meta keys
          alone.

        Both can be combined: ``data.clone(payload=arr, frame_index=5)``.
        """
        new_payload = self._payload if payload is _UNSET else payload
        new_meta = (
            self._meta.replace(**meta_changes) if meta_changes else self._meta
        )
        return IoData(self._type, payload=new_payload, meta=new_meta)

    def __repr__(self) -> str:
        # Image / SCALAR / MATRIX payloads expose a numpy ``shape``; the
        # non-numeric kinds don't, so fall back to ``repr(value)`` so the
        # __repr__ is meaningful for every payload kind.
        if hasattr(self._payload, "shape"):
            return f"IoData({self._type.name}, shape={self._payload.shape})"
        return f"IoData({self._type.name}, value={self._payload!r})"

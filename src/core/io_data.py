from __future__ import annotations

from enum import Enum

import numpy as np


class IoDataType(Enum):
    IMAGE = "Image"
    IMAGE_GREY = "ImageGrey"


#: Set of :class:`IoDataType` values that carry image payloads. Useful for
#: declaring input/output ports that accept colour or greyscale images
#: interchangeably, e.g. filters like Median and Scale that work on either.
IMAGE_TYPES: frozenset[IoDataType] = frozenset({IoDataType.IMAGE, IoDataType.IMAGE_GREY})


class IoData:
    """Envelope that carries a single image payload between nodes in a flow.

    All ports exchange :class:`IoData` objects. The :attr:`type` field acts
    as a discriminator so receiving nodes can decide how to handle the
    payload without inspecting the payload itself.

    Stream lifetime — the signal that a producer is done — is expressed
    out of band via :meth:`core.port.OutputPort.finish`, not through a
    payload value on this channel.
    """

    def __init__(self, type: IoDataType, image: np.ndarray) -> None:
        self._type = type
        self._image = image

    # ── Factory methods ────────────────────────────────────────────────────────

    @classmethod
    def from_image(cls, image: np.ndarray) -> IoData:
        """Wrap a (potentially multi-channel) image as :data:`IoDataType.IMAGE`."""
        return cls(IoDataType.IMAGE, image=image)

    @classmethod
    def from_greyscale(cls, image: np.ndarray) -> IoData:
        """Wrap a single-channel image as :data:`IoDataType.IMAGE_GREY`.

        The image is expected to be a 2-D ``uint8`` array. No shape check is
        enforced — callers are responsible for producing the right shape.
        """
        return cls(IoDataType.IMAGE_GREY, image=image)

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def type(self) -> IoDataType:
        return self._type

    @property
    def image(self) -> np.ndarray:
        return self._image

    def is_image(self) -> bool:
        """Return True if this carries an image payload (colour or greyscale)."""
        return self._type in IMAGE_TYPES

    def with_image(self, image: np.ndarray) -> IoData:
        """Return a new :class:`IoData` with the same type and a new payload.

        Use this in pass-through filters so the output type (IMAGE vs
        IMAGE_GREY) matches the input without the filter having to branch on
        it explicitly.
        """
        return IoData(self._type, image=image)

    def __repr__(self) -> str:
        shape = self._image.shape
        return f"IoData({self._type.name}, shape={shape})"

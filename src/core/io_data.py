from __future__ import annotations

from enum import Enum

import numpy as np


class IoDataType(Enum):
    IMAGE = "Image"
    IMAGE_GREY = "ImageGrey"
    END_OF_STREAM = "EndOfStream"


class IoData:
    """Envelope that carries data between nodes in a flow.

    All ports exchange IoData objects.  The type field acts as a discriminator
    so receiving nodes can decide how to handle the payload without inspecting
    the payload itself.

    EndOfStream is a control signal — it carries no payload and is accepted
    by every input port regardless of its declared accepted types.
    """

    def __init__(self, type: IoDataType, image: np.ndarray | None = None) -> None:
        self._type = type
        self._image = image

    # ── Factory methods ────────────────────────────────────────────────────────

    @classmethod
    def from_image(cls, image: np.ndarray) -> IoData:
        return cls(IoDataType.IMAGE, image=image)

    @classmethod
    def end_of_stream(cls) -> IoData:
        return cls(IoDataType.END_OF_STREAM)

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def type(self) -> IoDataType:
        return self._type

    @property
    def image(self) -> np.ndarray:
        if self._type != IoDataType.IMAGE:
            raise TypeError(f"IoData does not carry an image (type={self._type})")
        assert self._image is not None
        return self._image

    def is_end_of_stream(self) -> bool:
        return self._type == IoDataType.END_OF_STREAM

    def __repr__(self) -> str:
        if self._type == IoDataType.IMAGE:
            shape = self._image.shape if self._image is not None else "?"
            return f"IoData(IMAGE, shape={shape})"
        return f"IoData({self._type.value})"

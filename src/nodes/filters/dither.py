from __future__ import annotations

import math
from enum import IntEnum

import cv2
import numba
import numpy as np
from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase, NodeParam, NodeParamType
from core.port import InputPort, OutputPort


class DitherMethod(IntEnum):
    """Dithering algorithms supported by :class:`Dither`.

    Backed by :class:`IntEnum` so the integer representation (persisted
    in saved flows) round-trips cleanly: JSON stores the int, the
    setter accepts both ints and enum members, and the ``ENUM`` param
    widget renders a combo box of ``name``-based labels.
    """
    BAYER2          = 1
    BAYER4          = 2
    BAYER8          = 3
    NOISE           = 4
    FLOYD_STEINBERG = 5
    STUCKI          = 6
    ATKINSON        = 7
    BURKES          = 8
    SIERRA          = 9
    DIFFUSION_X     = 10
    DIFFUSION_XY    = 11


# Error-diffusion kernels as (n, 3) float64 arrays with columns
# [dy, dx, weight].  NumPy arrays (rather than Python tuples) are
# required for numba's nopython mode.
_DIFFUSION_KERNELS: dict[DitherMethod, np.ndarray] = {
    DitherMethod.FLOYD_STEINBERG: np.array([
        [0, +1, 7/16],
        [1, -1, 3/16], [1,  0, 5/16], [1, +1, 1/16],
    ], dtype=np.float64),
    DitherMethod.STUCKI: np.array([
        [0, +1, 8/42], [0, +2, 4/42],
        [1, -2, 2/42], [1, -1, 4/42], [1,  0, 8/42],
        [1, +1, 4/42], [1, +2, 2/42],
        [2, -2, 1/42], [2, -1, 2/42], [2,  0, 4/42],
        [2, +1, 2/42], [2, +2, 1/42],
    ], dtype=np.float64),
    DitherMethod.ATKINSON: np.array([
        [0, +1, 1/8], [0, +2, 1/8],
        [1, -1, 1/8], [1,  0, 1/8], [1, +1, 1/8],
        [2,  0, 1/8],
    ], dtype=np.float64),
    DitherMethod.BURKES: np.array([
        [0, +1, 8/32], [0, +2, 4/32],
        [1, -2, 2/32], [1, -1, 4/32], [1,  0, 8/32],
        [1, +1, 4/32], [1, +2, 2/32],
    ], dtype=np.float64),
    DitherMethod.SIERRA: np.array([
        [0, +1, 5/32], [0, +2, 3/32],
        [1, -2, 2/32], [1, -1, 4/32], [1,  0, 5/32],
        [1, +1, 4/32], [1, +2, 2/32],
        [2, -1, 2/32], [2,  0, 3/32], [2, +1, 2/32],
    ], dtype=np.float64),
    DitherMethod.DIFFUSION_X: np.array([
        [0, +1, 1.0],
    ], dtype=np.float64),
    DitherMethod.DIFFUSION_XY: np.array([
        [0, +1, 0.5], [1, 0, 0.5],
    ], dtype=np.float64),
}

# Bayer ordered-dither matrices (2×2, 4×4, 8×8).
_BAYER_MATRICES: dict[DitherMethod, np.ndarray] = {
    DitherMethod.BAYER2: np.array([
        [0, 2],
        [3, 1],
    ]),
    DitherMethod.BAYER4: np.array([
        [ 0,  8,  2, 10],
        [12,  4, 14,  6],
        [ 3, 11,  1,  9],
        [15,  7, 13,  5],
    ]),
    DitherMethod.BAYER8: np.array([
        [ 0, 32,  8, 40,  2, 34, 10, 42],
        [48, 16, 56, 24, 50, 18, 58, 26],
        [12, 44,  4, 36, 14, 46,  6, 38],
        [60, 28, 52, 20, 62, 30, 54, 22],
        [ 3, 35, 11, 43,  1, 33,  9, 41],
        [51, 19, 59, 27, 49, 17, 57, 25],
        [15, 47,  7, 39, 13, 45,  5, 37],
        [63, 31, 55, 23, 61, 29, 53, 21],
    ]),
}


class Dither(NodeBase):
    """Binary (black/white) dithering with a configurable algorithm.

    Reduces an image to two levels (0 / 255) using one of the classic
    ordered or error-diffusion schemes. Colour inputs are converted to
    grayscale first; the binary result is broadcast back to BGR so
    downstream nodes receive the expected 3-channel format.

    The error-diffusion inner loop is JIT-compiled by numba on first use
    (``@njit(cache=True)``), making it comparable in speed to the
    original OCVL implementation.
    """

    def __init__(self) -> None:
        super().__init__("Dither")
        self._method: DitherMethod = DitherMethod.STUCKI

        self._add_input(InputPort("image", {IoDataType.IMAGE}))
        self._add_output(OutputPort("image", {IoDataType.IMAGE}))

        self._apply_default_params()

    # ── Parameters ─────────────────────────────────────────────────────────────

    @property
    @override
    def params(self) -> list[NodeParam]:
        return [NodeParam(
            "method",
            NodeParamType.ENUM,
            {"default": DitherMethod.STUCKI, "enum": DitherMethod},
        )]

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def method(self) -> DitherMethod:
        return self._method

    @method.setter
    def method(self, value: int | DitherMethod) -> None:
        try:
            # DitherMethod(int) validates the integer and raises on unknown
            # values; passing a DitherMethod member just returns itself.
            self._method = DitherMethod(value)
        except ValueError as e:
            raise ValueError(
                f"method must be one of {[m.value for m in DitherMethod]} (got {value!r})"
            ) from e

    # ── NodeBase interface ─────────────────────────────────────────────────────

    @override
    def process(self) -> None:
        image: np.ndarray = self.inputs[0].data.image

        if image.ndim == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        method = self._method
        if method == DitherMethod.NOISE:
            out = _dither_noise(gray)
        elif method in _BAYER_MATRICES:
            out = _dither_bayer(gray, _BAYER_MATRICES[method])
        else:
            out = _dither_diffusion(gray, _DIFFUSION_KERNELS[method])

        out_bgr = cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)
        self.outputs[0].send(IoData.from_image(out_bgr))


# ── Dithering kernels ─────────────────────────────────────────────────────────

def _dither_noise(gray: np.ndarray) -> np.ndarray:
    noise = np.zeros_like(gray)
    cv2.randn(noise, 128, 50)
    return np.where(gray > noise, 255, 0).astype(np.uint8)


def _dither_bayer(gray: np.ndarray, bayer: np.ndarray) -> np.ndarray:
    """Vectorised ordered dither — no per-pixel loop needed."""
    h, w = gray.shape
    side = int(math.sqrt(bayer.size))
    reps = (h // side + 1, w // side + 1)
    tiled = np.tile(bayer, reps)[:h, :w]
    threshold = tiled * 255 / bayer.size
    return np.where(gray > threshold, 255, 0).astype(np.uint8)


@numba.njit(cache=True)
def _dither_diffusion(gray: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """Generic error-diffusion dither, JIT-compiled by numba.

    ``kernel`` is a (n, 3) float64 array with columns [dy, dx, weight].
    ``cache=True`` persists the compiled function to ``__pycache__`` so
    the JIT cost is paid only on the very first run after installation.
    """
    buf = gray.astype(np.float32).copy()
    h, w = buf.shape
    n = kernel.shape[0]

    for y in range(h):
        for x in range(w):
            old = buf[y, x]
            new = np.float32(255.0) if old > 127.0 else np.float32(0.0)
            buf[y, x] = new
            err = old - new
            if err == 0.0:
                continue
            for k in range(n):
                ny = y + int(kernel[k, 0])
                nx = x + int(kernel[k, 1])
                if 0 <= ny < h and 0 <= nx < w:
                    buf[ny, nx] += err * kernel[k, 2]

    return np.clip(buf, 0, 255).astype(np.uint8)

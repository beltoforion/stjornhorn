from __future__ import annotations

import cv2
import numba
import numpy as np
from typing_extensions import override

from core.io_data import IMAGE_TYPES, IoData, IoDataType
from core.node_base import NodeBase, NodeParamType
from core.port import InputPort, OutputPort


class SubpixelMosaic(NodeBase):
    """Render a BGR image as a stylised RGB sub-pixel mosaic.

    Each source pixel is scattered across three mono-channel sub-pixels
    on a 1.5× wider, 2× taller canvas, echoing the R/G/B arrangement of
    a physical display's shadow mask. Even and odd source columns use
    mirrored tile patterns so the sub-pixels pack without gaps.

    The raw mosaic distorts the source aspect ratio (vertical stretch
    by 4/3). When ``keep_aspect`` is enabled the canvas is nearest-
    neighbour rescaled to 2w × 2h so the output matches the source
    proportions. ``output_grayscale`` drops the colour and emits the
    per-pixel sample intensity as a single-channel image.

    Ported from OCVL's ``RbgJoinProcessor.__rgbify`` visualisation; the
    scatter kernel is JIT-compiled by numba (``@njit(cache=True)``).
    """

    def __init__(self) -> None:
        super().__init__("Subpixel Mosaic", section="Experimental")
        self._keep_aspect: bool = False
        self._output_grayscale: bool = False

        self._add_input(InputPort("image", {IoDataType.IMAGE}))
        self._add_input(InputPort(
            "keep_aspect",
            {IoDataType.BOOL},
            optional=True,
            default_value=False,
            metadata={"default": False, "param_type": NodeParamType.BOOL},
        ))
        self._add_input(InputPort(
            "output_grayscale",
            {IoDataType.BOOL},
            optional=True,
            default_value=False,
            metadata={"default": False, "param_type": NodeParamType.BOOL},
        ))
        self._add_output(OutputPort("image", set(IMAGE_TYPES)))

        self._apply_default_params()

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def keep_aspect(self) -> bool:
        return self._keep_aspect

    @keep_aspect.setter
    def keep_aspect(self, value: bool) -> None:
        self._keep_aspect = bool(value)

    @property
    def output_grayscale(self) -> bool:
        return self._output_grayscale

    @output_grayscale.setter
    def output_grayscale(self, value: bool) -> None:
        self._output_grayscale = bool(value)

    # ── NodeBase interface ─────────────────────────────────────────────────────

    @override
    def process_impl(self) -> None:
        image: np.ndarray = self.inputs[0].data.image
        if image.ndim != 3 or image.shape[2] != 3:
            raise ValueError("Subpixel Mosaic requires a 3-channel BGR image")

        mosaic = _rgbify(image)

        if self._keep_aspect:
            h, w, _ = image.shape
            mosaic = cv2.resize(mosaic, (2 * w, 2 * h), interpolation=cv2.INTER_NEAREST)

        if self._output_grayscale:
            # Every mosaic pixel carries exactly one non-zero channel, so
            # the per-pixel max equals the original source sample value
            # without luminance weighting — this preserves the raw sample
            # intensity in a single-channel image.
            grey = mosaic.max(axis=2).astype(np.uint8)
            self.outputs[0].send(IoData.from_greyscale(grey))
        else:
            self.outputs[0].send(IoData.from_image(mosaic))


@numba.njit(cache=True)
def _rgbify(image: np.ndarray) -> np.ndarray:
    """Scatter each source pixel's BGR samples across an upscaled canvas.

    Faithful port of OCVL's ``RbgJoinProcessor.__rgbify``. Output canvas
    is 1.5w × 2h; each source pixel contributes three mono-channel
    sub-pixels whose positions depend on whether the source column is
    even or odd so the tile patterns mesh.
    """
    h, w, _ = image.shape
    nh = h * 2
    nw = int(w * 1.5)
    rgb = np.zeros((nh, nw, 3), dtype=np.uint8)

    for x in range(w):
        for y in range(h):
            b = image[y, x, 0]
            g = image[y, x, 1]
            r = image[y, x, 2]
            if x % 2 == 0:
                ox = int(x * 1.5)
                rgb[2 * y + 0, ox,     1] = g
                rgb[2 * y + 0, ox + 1, 0] = b
                rgb[2 * y + 1, ox,     2] = r
            else:
                ox = 1 + int(x * 1.5 - 0.5)
                rgb[2 * y + 0, ox,     2] = r
                rgb[2 * y + 1, ox,     0] = b
                rgb[2 * y + 1, ox - 1, 1] = g
    return rgb

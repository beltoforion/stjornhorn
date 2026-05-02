from __future__ import annotations

from enum import IntEnum

import cv2
import numpy as np
from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase
from core.params import EnumParam
from core.port import InputPort, OutputPort


class Colormap(IntEnum):
    """Colormap selection for :class:`ApplyColormap`.

    Covers the perceptually-uniform family (VIRIDIS / PLASMA / MAGMA /
    INFERNO), the classic FFT / spectrogram palettes (JET, TURBO),
    plus a handful of utility palettes (HOT, BONE, PARULA, OCEAN,
    COOL).
    """
    VIRIDIS = cv2.COLORMAP_VIRIDIS
    PLASMA  = cv2.COLORMAP_PLASMA
    MAGMA   = cv2.COLORMAP_MAGMA
    INFERNO = cv2.COLORMAP_INFERNO
    JET     = cv2.COLORMAP_JET
    TURBO   = cv2.COLORMAP_TURBO
    HOT     = cv2.COLORMAP_HOT
    BONE    = cv2.COLORMAP_BONE
    PARULA  = cv2.COLORMAP_PARULA
    OCEAN   = cv2.COLORMAP_OCEAN
    COOL    = cv2.COLORMAP_COOL


class ApplyColormap(NodeBase):
    """Colorize a greyscale image with a chosen colormap.

    Maps each input intensity through the selected lookup table and
    emits a 3-channel BGR image. Expects the input to be tonemapped
    into 0..255 already; for HDR sources (raw FFT magnitudes, depth
    maps) apply log compression upstream.
    """

    # ``constant=True``: the palette is a build-time visualization
    # choice, not something a streaming source would animate per
    # frame, so the node renders the combo inline with no socket dot.
    colormap = EnumParam(
        Colormap,
        Colormap.VIRIDIS,
        constant=True,
        description=(
            "Lookup table used to colorize the greyscale input. "
            "VIRIDIS / PLASMA / MAGMA / INFERNO are perceptually "
            "uniform; JET and TURBO are the classic spectrogram "
            "/ FFT-magnitude palettes."
        ),
    )

    HEADER_ICON = "palette"

    def __init__(self) -> None:
        super().__init__("Apply Colormap", section="Color Spaces")
        self._add_input(InputPort("image", {IoDataType.IMAGE_GREY}))
        self._add_output(OutputPort("image", {IoDataType.IMAGE}))
        self._apply_default_params()

    @override
    def process_impl(self) -> None:
        image: np.ndarray = self.inputs[0].data.image
        if image.ndim != 2:
            raise ValueError(
                f"ApplyColormap expects a single-channel image, got shape {image.shape}"
            )
        if image.dtype != np.uint8:
            image = image.astype(np.uint8, copy=False)

        coloured = cv2.applyColorMap(image, int(self._colormap))
        self.outputs[0].send(IoData.from_image(coloured))

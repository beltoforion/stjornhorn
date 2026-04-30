from __future__ import annotations

from enum import IntEnum

import cv2
import numpy as np
from typing_extensions import override

from core.io_data import IMAGE_TYPES
from core.node_base import NodeBase
from core.params import EnumParam, IntParam
from core.port import InputPort, OutputPort


class Interpolation(IntEnum):
    """Resampling method used by :class:`Scale`."""
    NEAREST   = cv2.INTER_NEAREST
    LINEAR    = cv2.INTER_LINEAR
    CUBIC     = cv2.INTER_CUBIC
    AREA      = cv2.INTER_AREA
    LANCZOS4  = cv2.INTER_LANCZOS4


class Scale(NodeBase):
    """Resize an image by a percentage factor.

    ``scale_percent`` of 100 leaves the image unchanged.
    """

    scale_percent = IntParam(
        100,
        min=1,
        unit="%",
        description=(
            "Scale factor in percent. 100 leaves the image "
            "unchanged; 50 halves it; 200 doubles it."
        ),
    )
    interpolation = EnumParam(
        Interpolation,
        Interpolation.LINEAR,
        description=(
            "Resampling method. NEAREST is fast and pixelated; "
            "LINEAR / CUBIC / LANCZOS4 produce progressively "
            "smoother results at higher cost; AREA is preferred "
            "when downsampling."
        ),
    )

    def __init__(self) -> None:
        super().__init__("Scale", section="Transform")
        self._add_input(InputPort("image", set(IMAGE_TYPES)))
        self._add_output(OutputPort("image", set(IMAGE_TYPES)))
        self._apply_default_params()

    @override
    def process_impl(self) -> None:
        in_data = self.inputs[0].data
        image: np.ndarray = in_data.image
        h, w = image.shape[:2]
        factor = self._scale_percent / 100.0
        new_w = max(1, int(round(w * factor)))
        new_h = max(1, int(round(h * factor)))

        resized = cv2.resize(
            image,
            (new_w, new_h),
            interpolation=int(self._interpolation),
        )
        self.outputs[0].send(in_data.clone(payload=resized))

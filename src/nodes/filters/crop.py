from __future__ import annotations

import numpy as np
from typing_extensions import override

from core.io_data import IMAGE_TYPES
from core.node_base import NodeBase
from core.params import IntParam
from core.port import InputPort, OutputPort


class Crop(NodeBase):
    """Crop an image to a rectangular ROI.

    Parameters express the ROI in input-pixel coordinates: top-left
    ``(x, y)`` plus ``width`` and ``height``. The ROI is clamped to
    the input bounds, so the node always emits a positive-area image
    even if the user-specified rectangle reaches outside the input.
    """

    x = IntParam(
        0,
        min=0,
        unit="px",
        description="Left edge of the ROI in input-pixel coordinates.",
    )
    y = IntParam(
        0,
        min=0,
        unit="px",
        description="Top edge of the ROI in input-pixel coordinates.",
    )
    width = IntParam(
        100,
        min=1,
        unit="px",
        description=(
            "ROI width in pixels. Clamped to the input bounds, so "
            "the node always emits a positive-area image."
        ),
    )
    height = IntParam(
        100,
        min=1,
        unit="px",
        description="ROI height in pixels. Same clamping as width.",
    )

    def __init__(self) -> None:
        super().__init__("Crop", section="Transform")
        self._add_input(InputPort("image", set(IMAGE_TYPES)))
        self._add_output(OutputPort("image", set(IMAGE_TYPES)))
        self._apply_default_params()

    @override
    def process_impl(self) -> None:
        in_data = self.inputs[0].data
        image: np.ndarray = in_data.image
        h, w = image.shape[:2]

        x0 = max(0, min(self._x, w - 1))
        y0 = max(0, min(self._y, h - 1))
        x1 = max(x0 + 1, min(self._x + self._width,  w))
        y1 = max(y0 + 1, min(self._y + self._height, h))

        cropped = image[y0:y1, x0:x1]
        # cv2 ops downstream want a contiguous array; numpy slicing yields
        # a view, which is fine for read-only consumers but bites in-place
        # writers. Cheap insurance for ~100kB-100MB frames.
        cropped = np.ascontiguousarray(cropped)
        self.outputs[0].send(in_data.clone(payload=cropped))

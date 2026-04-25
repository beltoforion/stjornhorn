from __future__ import annotations

import numpy as np
from typing_extensions import override

from core.io_data import IMAGE_TYPES
from core.node_base import NodeBase, NodeParam, NodeParamType
from core.port import InputPort, OutputPort


class Crop(NodeBase):
    """Crop an image to a rectangular ROI.

    Parameters express the ROI in input-pixel coordinates: top-left
    ``(x, y)`` plus ``width`` and ``height``. The ROI is clamped to
    the input bounds, so the node always emits a positive-area image
    even if the user-specified rectangle reaches outside the input.
    """

    def __init__(self) -> None:
        super().__init__("Crop", section="Transform")
        self._x:      int = 0
        self._y:      int = 0
        self._width:  int = 100
        self._height: int = 100

        self._add_input(InputPort("image", set(IMAGE_TYPES)))
        self._add_output(OutputPort("image", set(IMAGE_TYPES)))

        self._apply_default_params()

    @property
    @override
    def params(self) -> list[NodeParam]:
        return [
            NodeParam("x",      NodeParamType.INT, {"default": 0}),
            NodeParam("y",      NodeParamType.INT, {"default": 0}),
            NodeParam("width",  NodeParamType.INT, {"default": 100}),
            NodeParam("height", NodeParamType.INT, {"default": 100}),
        ]

    @property
    def x(self) -> int:
        return self._x

    @x.setter
    def x(self, value: int) -> None:
        self._x = int(value)

    @property
    def y(self) -> int:
        return self._y

    @y.setter
    def y(self, value: int) -> None:
        self._y = int(value)

    @property
    def width(self) -> int:
        return self._width

    @width.setter
    def width(self, value: int) -> None:
        v = int(value)
        if v < 1:
            raise ValueError(f"width must be >= 1 (got {v})")
        self._width = v

    @property
    def height(self) -> int:
        return self._height

    @height.setter
    def height(self, value: int) -> None:
        v = int(value)
        if v < 1:
            raise ValueError(f"height must be >= 1 (got {v})")
        self._height = v

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
        self.outputs[0].send(in_data.with_image(cropped))

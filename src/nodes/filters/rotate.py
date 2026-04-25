from __future__ import annotations

import cv2
import numpy as np
from typing_extensions import override

from core.io_data import IMAGE_TYPES
from core.node_base import NodeBase, NodeParam, NodeParamType
from core.port import InputPort, OutputPort


class Rotate(NodeBase):
    """Rotate an image around its centre by ``angle`` degrees.

    Positive ``angle`` rotates counter-clockwise (matching
    :func:`cv2.getRotationMatrix2D` and the existing Overlay node).
    With ``expand=True`` the output canvas grows to fit the rotated
    image so no pixels are clipped; with ``expand=False`` the output
    keeps the input dimensions and corners may fall outside.
    """

    def __init__(self) -> None:
        super().__init__("Rotate", section="Transform")
        self._angle:  float = 0.0
        self._expand: bool  = True

        self._add_input(InputPort("image", set(IMAGE_TYPES)))
        self._add_output(OutputPort("image", set(IMAGE_TYPES)))

        self._apply_default_params()

    @property
    @override
    def params(self) -> list[NodeParam]:
        return [
            NodeParam("angle",  NodeParamType.FLOAT, {"default": 0.0}),
            NodeParam("expand", NodeParamType.BOOL,  {"default": True}),
        ]

    @property
    def angle(self) -> float:
        return self._angle

    @angle.setter
    def angle(self, value: float) -> None:
        self._angle = float(value)

    @property
    def expand(self) -> bool:
        return self._expand

    @expand.setter
    def expand(self, value: bool) -> None:
        self._expand = bool(value)

    @override
    def process_impl(self) -> None:
        in_data = self.inputs[0].data
        image: np.ndarray = in_data.image
        h, w = image.shape[:2]
        cx, cy = w * 0.5, h * 0.5

        m = cv2.getRotationMatrix2D((cx, cy), self._angle, 1.0)

        if self._expand:
            cos = abs(m[0, 0])
            sin = abs(m[0, 1])
            new_w = int(round(h * sin + w * cos))
            new_h = int(round(h * cos + w * sin))
            m[0, 2] += (new_w * 0.5) - cx
            m[1, 2] += (new_h * 0.5) - cy
            out_size = (new_w, new_h)
        else:
            out_size = (w, h)

        rotated = cv2.warpAffine(image, m, out_size, flags=cv2.INTER_LINEAR)
        self.outputs[0].send(in_data.with_image(rotated))

from __future__ import annotations

import cv2
import numpy as np
from typing_extensions import override

from core.io_data import IMAGE_TYPES
from core.node_base import NodeBase
from core.port import InputPort, OutputPort


class Normalize(NodeBase):
    """Equalise the histogram of an image.

    Operates on 8-bit data. Accepts colour or greyscale and emits the
    same type; colour inputs are equalised per channel.
    """

    def __init__(self) -> None:
        super().__init__("Normalize", section="Processing")
        self._add_input(InputPort("image", set(IMAGE_TYPES)))
        self._add_output(OutputPort("image", set(IMAGE_TYPES)))

    @override
    def process_impl(self) -> None:
        in_data = self.inputs[0].data
        image = in_data.image

        if image.ndim == 2:
            result = cv2.equalizeHist(image)
        else:
            # equalizeHist is single-channel only; split/apply/merge to
            # keep a consistent 3-channel BGR output for downstream nodes.
            channels = cv2.split(image)
            equalised = [cv2.equalizeHist(c) for c in channels]
            result = cv2.merge(equalised)

        self.outputs[0].send(in_data.clone(payload=result))

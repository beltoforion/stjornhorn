from __future__ import annotations

import cv2
import numpy as np
from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase, NodeParam
from core.port import InputPort, OutputPort


class Normalize(NodeBase):
    """Equalise the histogram of an image.

    Applies ``cv2.equalizeHist`` — a per-channel operation on 8-bit
    single-channel data. For BGR inputs each channel is equalised
    independently (matching how downstream nodes expect a 3-channel
    image). Ported from the original OCVL ``NormalizeProcessor``.
    """

    def __init__(self) -> None:
        super().__init__("Normalize", section="Processing")
        self._add_input(InputPort("image", {IoDataType.IMAGE}))
        self._add_output(OutputPort("image", {IoDataType.IMAGE}))

    @property
    @override
    def params(self) -> list[NodeParam]:
        return []

    @override
    def process(self) -> None:
        image: np.ndarray = self.inputs[0].data.image

        if image.ndim == 2:
            result = cv2.equalizeHist(image)
        else:
            # equalizeHist is single-channel only; split/apply/merge to
            # keep a consistent 3-channel BGR output for downstream nodes.
            channels = cv2.split(image)
            equalised = [cv2.equalizeHist(c) for c in channels]
            result = cv2.merge(equalised)

        self.outputs[0].send(IoData.from_image(result))

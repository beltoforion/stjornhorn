from __future__ import annotations

import cv2
import numpy as np
from typing_extensions import override

from core.io_data import IMAGE_TYPES
from core.node_base import NodeBase
from core.port import InputPort, OutputPort


class FrameDifference(NodeBase):
    """Per-pixel absolute difference between the current and previous frame.

    A baseline change-detector for video streams. Holds the previous
    frame internally; the buffer is reset at the start of every flow
    run. The first frame in a stream emits an all-zero image (same
    shape and dtype as the input) because there is no prior frame to
    diff against. Frames whose shape changes mid-stream also reset the
    buffer rather than raising.
    """

    def __init__(self) -> None:
        super().__init__("Frame Difference", section="Temporal")
        self._prev_frame: np.ndarray | None = None

        self._add_input(InputPort("image", set(IMAGE_TYPES)))
        self._add_output(OutputPort("image", set(IMAGE_TYPES)))

    @override
    def _before_run_impl(self) -> None:
        super()._before_run_impl()
        self._prev_frame = None

    @override
    def process_impl(self) -> None:
        in_data = self.inputs[0].data
        image: np.ndarray = in_data.image

        if self._prev_frame is None or self._prev_frame.shape != image.shape:
            diff = np.zeros_like(image)
        else:
            diff = cv2.absdiff(image, self._prev_frame)

        self._prev_frame = image.copy()
        self.outputs[0].send(in_data.with_image(diff))

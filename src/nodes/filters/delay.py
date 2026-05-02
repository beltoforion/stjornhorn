from __future__ import annotations

import time

from typing_extensions import override

from core.io_data import IMAGE_TYPES
from core.node_base import NodeBase
from core.params import FloatParam
from core.port import InputPort, OutputPort


class Delay(NodeBase):
    """Pace a stream by sleeping for ``delay_seconds`` between frames.

    The image payload is forwarded unchanged. Useful as a "slideshow"
    knob or to make per-frame status updates visible during
    development.
    """

    delay_seconds = FloatParam(
        5.0,
        min=0.0,
        unit="s",
        description=(
            "How long to sleep between frames, in seconds. "
            "Set to 0 to disable the pacing entirely."
        ),
    )

    HEADER_ICON = "schedule"

    def __init__(self) -> None:
        super().__init__("Delay", section="UI")
        self._add_input(InputPort("image", set(IMAGE_TYPES)))
        self._add_output(OutputPort("image", set(IMAGE_TYPES)))
        self._apply_default_params()

    @override
    def process_impl(self) -> None:
        in_data = self.inputs[0].data
        time.sleep(self._delay_seconds)
        self.outputs[0].send(in_data)

from __future__ import annotations

import cv2
import numpy as np
from typing_extensions import override

from core.io_data import IMAGE_TYPES
from core.node_base import NodeBase, NodeParam, NodeParamType
from core.port import InputPort, OutputPort

# OpenCV interpolation flags — exposed as a small int param so the UI
# can offer "nearest / linear / cubic / area / lanczos4" as plain values.
_INTERPOLATIONS: dict[int, int] = {
    0: cv2.INTER_NEAREST,
    1: cv2.INTER_LINEAR,
    2: cv2.INTER_CUBIC,
    3: cv2.INTER_AREA,
    4: cv2.INTER_LANCZOS4,
}


class Scale(NodeBase):
    """Resize an image by a percentage factor.

    The input is resized by ``scale_percent`` (100 = no change). Ported
    from the original OCVL ``ScaleProcessor`` — the target-size mode is
    omitted here because there is no tuple param type; if an absolute
    size is needed, compute the matching scale factor.
    """

    def __init__(self) -> None:
        super().__init__("Scale", section="Transform")
        self._scale_percent: int = 100
        self._interpolation: int = 1  # Linear

        self._add_input(InputPort("image", set(IMAGE_TYPES)))
        self._add_output(OutputPort("image", set(IMAGE_TYPES)))

        self._apply_default_params()

    # ── Parameters ─────────────────────────────────────────────────────────────

    @property
    @override
    def params(self) -> list[NodeParam]:
        return [
            NodeParam("scale_percent", NodeParamType.INT, {"default": 100}),
            # 0=nearest, 1=linear, 2=cubic, 3=area, 4=lanczos4
            NodeParam("interpolation", NodeParamType.INT, {"default": 1}),
        ]

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def scale_percent(self) -> int:
        return self._scale_percent

    @scale_percent.setter
    def scale_percent(self, value: int) -> None:
        v = int(value)
        if v <= 0:
            raise ValueError(f"scale_percent must be > 0 (got {v})")
        self._scale_percent = v

    @property
    def interpolation(self) -> int:
        return self._interpolation

    @interpolation.setter
    def interpolation(self, value: int) -> None:
        v = int(value)
        if v not in _INTERPOLATIONS:
            raise ValueError(
                f"interpolation must be one of {sorted(_INTERPOLATIONS)} (got {v})"
            )
        self._interpolation = v

    # ── NodeBase interface ─────────────────────────────────────────────────────

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
            interpolation=_INTERPOLATIONS[self._interpolation],
        )
        self.outputs[0].send(in_data.with_image(resized))

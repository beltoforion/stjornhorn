from __future__ import annotations

import cv2
import numpy as np
from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase, NodeParam, NodeParamType
from core.port import InputPort, OutputPort


class Ncc(NodeBase):
    """Normalised cross-correlation template matching.

    Wraps ``cv2.matchTemplate`` with ``TM_CCORR_NORMED`` and rescales the
    score map to a ``uint8`` greyscale image. The ``template`` input is
    the pattern searched for within ``image``. Both inputs must be
    single-channel greyscale. Ported from the original OCVL
    ``NccProcessor``.

    With ``retain_size=True`` (default) the match map is pasted into a
    canvas the same size as ``image`` and offset by half the template
    size, so each response sits at the pixel it corresponds to (template
    centre). With ``retain_size=False`` the raw ``matchTemplate`` output
    is emitted, which is smaller than the input by ``template.shape - 1``
    on each axis.
    """

    def __init__(self) -> None:
        super().__init__("NCC", section="Processing")
        self._retain_size: bool = True

        self._add_input(InputPort("image", {IoDataType.IMAGE_GREY}))
        self._add_input(InputPort("template", {IoDataType.IMAGE_GREY}))
        self._add_output(OutputPort("image", {IoDataType.IMAGE_GREY}))

        self._apply_default_params()

    # ── Parameters ─────────────────────────────────────────────────────────────

    @property
    @override
    def params(self) -> list[NodeParam]:
        return [NodeParam("retain_size", NodeParamType.BOOL, {"default": True})]

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def retain_size(self) -> bool:
        return self._retain_size

    @retain_size.setter
    def retain_size(self, value: bool) -> None:
        self._retain_size = bool(value)

    # ── NodeBase interface ─────────────────────────────────────────────────────

    @override
    def process_impl(self) -> None:
        image: np.ndarray = self.inputs[0].data.image
        template: np.ndarray = self.inputs[1].data.image

        res = cv2.matchTemplate(image, template, cv2.TM_CCORR_NORMED)
        res = cv2.normalize(
            (res * 255).astype(np.uint8),
            None,
            alpha=0,
            beta=255,
            norm_type=cv2.NORM_MINMAX,
        )

        if self._retain_size:
            h_t, w_t = template.shape[:2]
            h_orig, w_orig = image.shape[:2]
            h_m, w_m = res.shape[:2]

            y0 = h_t // 2
            x0 = w_t // 2

            canvas = np.zeros((h_orig, w_orig), dtype=np.uint8)
            canvas[y0:y0 + h_m, x0:x0 + w_m] = res
            out = canvas
        else:
            out = res

        self.outputs[0].send(IoData.from_greyscale(out))

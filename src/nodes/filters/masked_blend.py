from __future__ import annotations

import cv2
import numpy as np
from typing_extensions import override

from core.io_data import IMAGE_TYPES, IoData, IoDataType
from core.node_base import NodeBase
from core.port import InputPort, OutputPort


class MaskedBlend(NodeBase):
    """Per-pixel blend of two images driven by a greyscale mask.

    For every pixel ``out = base * (1 - m) + overlay * m`` with
    ``m = mask / 255`` — black mask emits ``base``, white mask emits
    ``overlay``, intermediate values cross-fade. Unlike
    :class:`~nodes.filters.overlay.Overlay` (which uses a uniform
    alpha or BGRA channel), the mask is a separate input so any
    greyscale producer can drive it.

    ``base`` and ``overlay`` must have identical ``H x W``; if either
    is colour, the output is colour and the other is promoted. The
    ``mask`` is reduced to a single channel and resized to ``base``
    if it differs.
    """

    def __init__(self) -> None:
        super().__init__("Masked Blend", section="Composit")

        self._add_input(InputPort("base", set(IMAGE_TYPES)))
        self._add_input(InputPort("overlay", set(IMAGE_TYPES)))
        self._add_input(InputPort("mask", set(IMAGE_TYPES)))
        self._add_output(OutputPort("image", set(IMAGE_TYPES)))

    @override
    def process_impl(self) -> None:
        base_data    = self.inputs[0].data
        overlay_data = self.inputs[1].data
        mask_data    = self.inputs[2].data

        any_color = (
            base_data.type == IoDataType.IMAGE
            or overlay_data.type == IoDataType.IMAGE
        )

        def to_canvas(d: IoData) -> np.ndarray:
            img = d.image
            if any_color and d.type == IoDataType.IMAGE_GREY:
                return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
            return img

        def strip_alpha(img: np.ndarray) -> np.ndarray:
            """Drop the alpha channel of a BGRA input so blend math holds."""
            if img.ndim == 3 and img.shape[2] == 4:
                return img[:, :, :3]
            return img

        base    = strip_alpha(to_canvas(base_data))
        overlay = strip_alpha(to_canvas(overlay_data))

        if base.shape != overlay.shape:
            raise ValueError(
                f"MaskedBlend: base shape {base.shape} != "
                f"overlay shape {overlay.shape}"
            )

        # Reduce the mask to a single 2-D plane regardless of how it
        # arrived. ImageSource promotes greyscale PNGs to BGR, so a
        # gradient PNG dropped on the mask input arrives as a 3-channel
        # IMAGE — keeping the first channel matches the common case
        # where every channel carries the same gradient.
        mask_img = mask_data.image
        if mask_img.ndim == 3:
            mask_img = mask_img[:, :, 0]

        base_h, base_w = base.shape[:2]
        if mask_img.shape[:2] != (base_h, base_w):
            mask_img = cv2.resize(
                mask_img, (base_w, base_h), interpolation=cv2.INTER_LINEAR
            )

        # Float32 intermediate — uint8 multiply would overflow, and
        # float32 is cheap enough on the per-frame hot path.
        m = mask_img.astype(np.float32) * (1.0 / 255.0)
        if base.ndim == 3:
            m = m[:, :, None]  # broadcast across BGR channels

        blended = base.astype(np.float32) * (1.0 - m) \
                + overlay.astype(np.float32) * m
        result = np.clip(blended, 0.0, 255.0).astype(np.uint8)

        if any_color:
            self.outputs[0].send(IoData.from_image(result))
        else:
            self.outputs[0].send(IoData.from_greyscale(result))

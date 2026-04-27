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
    ``m = mask / 255`` — the mask's intensity controls how much of
    the overlay shows through. A black mask emits the base unchanged,
    a white mask emits the overlay unchanged, and intermediate values
    cross-fade smoothly. This is the missing primitive that
    :class:`~nodes.filters.overlay.Overlay` doesn't cover: Overlay
    blends with a *uniform* alpha (or a per-pixel alpha embedded in a
    BGRA overlay), whereas this node accepts the mask as a separate
    input — so you can drive the mask with any greyscale producer
    (gradient image, threshold output, distance field, …) instead of
    having to bake it into the overlay's alpha channel.

    Type strategy:
      If either ``base`` or ``overlay`` is colour
      (:data:`IoDataType.IMAGE`), any greyscale image input is
      promoted to BGR via ``cv2.cvtColor(..., COLOR_GRAY2BGR)`` and
      the output is emitted as ``IMAGE``. If both are greyscale, the
      output stays greyscale. The ``mask`` input accepts either type
      and is reduced to a single channel internally — feeding a 3- or
      4-channel image keeps the first channel (cheap, and matches the
      common case of a greyscale gradient that
      :class:`~nodes.sources.image_source.ImageSource` has promoted
      to BGR).

    Size strategy:
      ``base`` and ``overlay`` must have identical ``H x W``. The
      ``mask`` is resized to ``base``'s ``H x W`` if it differs, with
      :data:`cv2.INTER_LINEAR` so a small procedural gradient can
      drive a full-resolution stream without the user having to match
      sizes manually.
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

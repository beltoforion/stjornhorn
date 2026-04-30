from __future__ import annotations

from enum import IntEnum

import cv2
import numpy as np
from typing_extensions import override

from core.io_data import IMAGE_TYPES
from core.node_base import NodeBase
from core.params import EnumParam, IntParam
from core.port import InputPort, OutputPort


class ResizeMethod(IntEnum):
    """Strategy used by :class:`Resize` to map the source onto the
    target ``(width, height)``.
    """
    #: Stretch X and Y independently to fit the target; aspect ratio
    #: is not preserved.
    SCALE        = 0

    #: Centre the source on a target-sized canvas; crop overflow,
    #: fill uncovered areas with black. Pixel scale is preserved.
    CROP_OR_FILL = 1

    #: Scale uniformly to the largest size that fits inside the target,
    #: then centre on a black canvas (letterbox / pillarbox).
    BEST_FIT     = 2


class Resize(NodeBase):
    """Resize an image to an explicit ``(width, height)`` using one of
    three layout strategies (see :class:`ResizeMethod`).

    Output dtype and channel count match the input. Letterbox / crop
    fills are black — for BGRA inputs that means ``alpha=0``
    (transparent black).
    """

    #: Interpolation passed to :func:`cv2.resize` for both ``SCALE``
    #: and ``BEST_FIT``. Linear strikes the usual balance between
    #: speed and quality; not exposed as a param for now to keep the
    #: node small. Bring it forward (port-style ENUM, mirroring
    #: :class:`Scale.interpolation`) if downstream use cases need
    #: bilinear vs. bicubic vs. area control.
    _INTERPOLATION: int = cv2.INTER_LINEAR

    width = IntParam(
        256,
        min=1,
        unit="px",
        description="Target width in pixels.",
    )
    height = IntParam(
        256,
        min=1,
        unit="px",
        description="Target height in pixels.",
    )
    # ``constant=True``: the resize strategy is a build-time choice,
    # not something a streaming source would animate per frame.
    # Renders inline with no socket dot.
    method = EnumParam(
        ResizeMethod,
        ResizeMethod.SCALE,
        constant=True,
        description=(
            "Layout strategy. SCALE stretches to fit. CROP_OR_FILL "
            "preserves aspect ratio and either crops or pads. "
            "BEST_FIT preserves aspect ratio and pads only."
        ),
    )

    def __init__(self) -> None:
        super().__init__("Resize", section="Transform")
        self._add_input(InputPort("image", set(IMAGE_TYPES)))
        self._add_output(OutputPort("image", set(IMAGE_TYPES)))
        self._apply_default_params()

    @override
    def process_impl(self) -> None:
        in_data = self.inputs[0].data
        image: np.ndarray = in_data.image
        target_w, target_h = self._width, self._height

        if self._method is ResizeMethod.SCALE:
            out = cv2.resize(
                image, (target_w, target_h), interpolation=self._INTERPOLATION,
            )
        elif self._method is ResizeMethod.CROP_OR_FILL:
            out = self._crop_or_fill(image, target_w, target_h)
        else:  # BEST_FIT
            out = self._best_fit(image, target_w, target_h)

        self.outputs[0].send(in_data.clone(payload=out))

    # ── Layout strategies ─────────────────────────────────────────────────────

    @staticmethod
    def _crop_or_fill(image: np.ndarray, target_w: int, target_h: int) -> np.ndarray:
        """Centre the source on a target-sized black canvas, cropping
        wherever the source overlaps off-canvas.

        Same formula in both axes: copy the largest centred region of
        the source that fits inside the target into the matching
        centred region of the canvas. When the source is larger in an
        axis, the source is cropped (canvas is fully covered along
        that axis); when it's smaller, the canvas keeps a black
        margin (source is fully placed along that axis). Pixel scale
        is preserved — the source isn't resampled.
        """
        h, w = image.shape[:2]
        out = _zero_canvas_like(image, target_w, target_h)

        copy_w = min(w, target_w)
        copy_h = min(h, target_h)
        # Source-side anchor: when the source is larger than the
        # target, start the crop so the *centre pixel* of the source
        # lands at the *centre pixel* of the canvas. When the source
        # is smaller, the source's full extent is copied (src_x0=0).
        src_x0 = (w - copy_w) // 2
        src_y0 = (h - copy_h) // 2
        # Destination-side anchor: when the source is smaller than the
        # target, leave a black margin around it; when larger, the
        # destination is fully written (dst_x0=0).
        dst_x0 = (target_w - copy_w) // 2
        dst_y0 = (target_h - copy_h) // 2

        out[dst_y0:dst_y0 + copy_h, dst_x0:dst_x0 + copy_w] = (
            image[src_y0:src_y0 + copy_h, src_x0:src_x0 + copy_w]
        )
        return out

    @classmethod
    def _best_fit(cls, image: np.ndarray, target_w: int, target_h: int) -> np.ndarray:
        """Scale the source uniformly to the largest size that still
        fits inside the target, then centre on a black canvas.

        Aspect ratio is preserved; whichever axis is the limiting one
        ends up touching the canvas edges, the other ends up with a
        black margin (letterbox or pillarbox). For a perfect
        aspect-ratio match between source and target, the resized
        source covers the canvas exactly with no margin.
        """
        h, w = image.shape[:2]
        # Both ratios > 0 because width / height setters reject < 1.
        scale = min(target_w / w, target_h / h)
        new_w = max(1, int(round(w * scale)))
        new_h = max(1, int(round(h * scale)))
        resized = cv2.resize(
            image, (new_w, new_h), interpolation=cls._INTERPOLATION,
        )
        out = _zero_canvas_like(image, target_w, target_h)
        dst_x0 = (target_w - new_w) // 2
        dst_y0 = (target_h - new_h) // 2
        out[dst_y0:dst_y0 + new_h, dst_x0:dst_x0 + new_w] = resized
        return out


def _zero_canvas_like(image: np.ndarray, target_w: int, target_h: int) -> np.ndarray:
    """Allocate a target-sized canvas with the same dtype and channel
    count as *image*, zero-filled. Greyscale (2-D), BGR (3 channels)
    and BGRA (4 channels) are all handled uniformly — a 4-channel
    canvas's alpha lane stays at 0, which is "transparent black"; if
    that's the wrong fill for a downstream consumer, drop the alpha
    via :class:`~nodes.filters.rgba_split.RgbaSplit` before resizing.
    """
    if image.ndim == 2:
        return np.zeros((target_h, target_w), dtype=image.dtype)
    return np.zeros((target_h, target_w, image.shape[2]), dtype=image.dtype)

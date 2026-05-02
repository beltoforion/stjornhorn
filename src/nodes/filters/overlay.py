from __future__ import annotations

import cv2
import numpy as np
from typing_extensions import override

from core.io_data import IMAGE_TYPES, IoData, IoDataType
from core.node_base import NodeBase
from core.params import ClampedFloatParam, FloatParam, IntParam
from core.port import InputPort, OutputPort


class Overlay(NodeBase):
    """Composite an overlay image onto a base image.

    The overlay is optionally resized by ``scale``, rotated by
    ``angle`` degrees (counter-clockwise around its centre, with the
    bounding box expanded so no pixels are lost) and blended onto the
    base so the overlay's **centre** lands at ``(xpos, ypos)`` with
    opacity ``alpha``. The output canvas matches the base; pixels
    outside it are clipped.

    If either input is colour the output is colour (greyscale inputs
    are promoted); otherwise the output stays greyscale. A BGRA
    overlay's alpha channel is used as a per-pixel mask and the
    ``alpha`` parameter then acts as a global multiplier on top.
    """

    angle = FloatParam(
        0.0,
        unit="deg",
        description=(
            "Overlay rotation in degrees, counter-clockwise around "
            "its centre. The bounding box is expanded so no pixels "
            "are lost."
        ),
    )
    scale = FloatParam(
        1.0,
        min=0.0,
        min_exclusive=True,
        description="Overlay scale factor. 1.0 = unchanged.",
    )
    xpos = IntParam(
        0,
        unit="px",
        description=(
            "X-coordinate (in base-image pixels) of the overlay's "
            "centre — not its top-left corner."
        ),
    )
    ypos = IntParam(
        0,
        unit="px",
        description=(
            "Y-coordinate (in base-image pixels) of the overlay's "
            "centre — not its top-left corner."
        ),
    )
    alpha = ClampedFloatParam(
        1.0,
        min=0.0,
        max=1.0,
        description=(
            "Global opacity multiplier in [0, 1]. Out-of-range values "
            "clamp rather than raise so a sweep into negative or >1 "
            "territory just saturates. For BGRA overlays this "
            "multiplies on top of the per-pixel alpha channel."
        ),
    )

    HEADER_ICON = "layers"

    def __init__(self) -> None:
        super().__init__("Overlay", section="Composit")
        self._add_input(InputPort("image", set(IMAGE_TYPES)))
        self._add_input(InputPort("overlay", set(IMAGE_TYPES)))
        self._add_output(OutputPort("image", set(IMAGE_TYPES)))
        self._apply_default_params()

    @override
    def process_impl(self) -> None:
        base_data    = self.inputs[0].data
        overlay_data = self.inputs[1].data

        # ``self._angle`` (and every other param-driven attribute) has
        # already been populated by NodeBase before this method runs:
        # the framework reads each connected input port and writes its
        # current value into the matching ``self._<port_name>``,
        # restoring the user-set fallback after the call. So we just
        # read self._angle directly — no per-port branching here.

        any_color = (
            base_data.type == IoDataType.IMAGE
            or overlay_data.type == IoDataType.IMAGE
        )

        def to_canvas(d: IoData) -> np.ndarray:
            if any_color and d.type == IoDataType.IMAGE_GREY:
                return cv2.cvtColor(d.image, cv2.COLOR_GRAY2BGR)
            return d.image

        def strip_alpha(img: np.ndarray) -> np.ndarray:
            """Drop the alpha channel of a BGRA base so BGR blending math holds."""
            if img.ndim == 3 and img.shape[2] == 4:
                return img[:, :, :3]
            return img

        # ── Skip path 1: alpha == 0 ───────────────────────────────────────
        # Overlay is invisible — no warp, no copy, no blend. Forward the
        # (possibly grey→BGR promoted, alpha-stripped) base straight through.
        if self._alpha == 0.0:
            self._emit(strip_alpha(to_canvas(base_data)), any_color)
            return

        overlay_src = to_canvas(overlay_data)
        has_per_pixel_alpha = overlay_src.ndim == 3 and overlay_src.shape[2] == 4
        src_h, src_w = overlay_src.shape[:2]

        # ── Predict the transformed overlay's bounding box (no warp yet) ──
        # cheap enough to always compute, so we can decide whether to
        # bother with the expensive warpAffine / resize / base.copy().
        rotates = self._angle % 360.0 != 0.0
        if rotates:
            center = (src_w / 2.0, src_h / 2.0)
            M = cv2.getRotationMatrix2D(center, self._angle, self._scale)
            cos = abs(M[0, 0])
            sin = abs(M[0, 1])
            out_w = max(1, int(round(src_h * sin + src_w * cos)))
            out_h = max(1, int(round(src_h * cos + src_w * sin)))
        elif self._scale != 1.0:
            out_w = max(1, int(round(src_w * self._scale)))
            out_h = max(1, int(round(src_h * self._scale)))
        else:
            out_w, out_h = src_w, src_h

        base_src = strip_alpha(to_canvas(base_data))
        base_h, base_w = base_src.shape[:2]

        # ``(xpos, ypos)`` denotes the *centre* of the (rotated, scaled)
        # overlay's bounding box on the base — translate to the top-left
        # corner that the rest of the placement math expects.
        top_left_x = self._xpos - out_w // 2
        top_left_y = self._ypos - out_h // 2

        # Destination rectangle on the base, clipped to the base bounds.
        x0 = max(top_left_x, 0)
        y0 = max(top_left_y, 0)
        x1 = min(top_left_x + out_w, base_w)
        y1 = min(top_left_y + out_h, base_h)

        # ── Skip path 2: transformed overlay misses the base entirely ─────
        # Same deal — pass the base through without warping or copying.
        if x0 >= x1 or y0 >= y1:
            self._emit(base_src, any_color)
            return

        # ── Execute the transform + composite ─────────────────────────────
        if rotates:
            M[0, 2] += (out_w / 2.0) - center[0]
            M[1, 2] += (out_h / 2.0) - center[1]
            overlay = cv2.warpAffine(
                overlay_src, M, (out_w, out_h), flags=cv2.INTER_LINEAR
            )
        elif self._scale != 1.0:
            overlay = cv2.resize(
                overlay_src, (out_w, out_h), interpolation=cv2.INTER_LINEAR
            )
        else:
            overlay = overlay_src

        base = base_src.copy()

        # Matching rectangle inside the overlay (accounts for the
        # centre-anchored placement shifting the overlay off the
        # top-left edge of the base).
        ox0 = x0 - top_left_x
        oy0 = y0 - top_left_y
        ox1 = ox0 + (x1 - x0)
        oy1 = oy0 + (y1 - y0)

        roi     = base[y0:y1, x0:x1]
        ov_crop = overlay[oy0:oy1, ox0:ox1]

        if has_per_pixel_alpha:
            # Per-pixel alpha path: normalise the alpha plane to [0, 1],
            # multiply by the global ``alpha`` slider, broadcast to 3
            # channels and blend. Using float32 keeps the arithmetic cheap
            # on a per-frame hot path while avoiding uint8 overflow.
            ov_bgr    = ov_crop[:, :, :3]
            ov_alpha  = ov_crop[:, :, 3].astype(np.float32) * (self._alpha / 255.0)
            ov_alpha  = ov_alpha[:, :, None]  # (H, W, 1) for broadcast
            blended = ov_bgr.astype(np.float32) * ov_alpha \
                    + roi.astype(np.float32) * (1.0 - ov_alpha)
            base[y0:y1, x0:x1] = blended.astype(np.uint8)
        else:
            blended = cv2.addWeighted(ov_crop, self._alpha, roi, 1.0 - self._alpha, 0.0)
            base[y0:y1, x0:x1] = blended

        self._emit(base, any_color)

    def _emit(self, image: np.ndarray, any_color: bool) -> None:
        if any_color:
            self.outputs[0].send(IoData.from_image(image))
        else:
            self.outputs[0].send(IoData.from_greyscale(image))

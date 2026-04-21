from __future__ import annotations

import cv2
import numpy as np
from typing_extensions import override

from core.io_data import IMAGE_TYPES, IoData, IoDataType
from core.node_base import NodeBase, NodeParam
from core.port import InputPort, OutputPort


class Merge(NodeBase):
    """Composite up to four images into a 2x2 grid.

    Inputs ``top_left``, ``top_right``, ``bottom_left`` and ``bottom_right``
    are pasted into the corresponding quadrant of a single output canvas.
    Not every input has to be connected — missing quadrants become black.

    Size strategy (per row / per column):
      * Top-row height  = max(top_left.h, top_right.h)
      * Bottom-row ""   = max(bottom_left.h, bottom_right.h)
      * Left-column width  = max(top_left.w, bottom_left.w)
      * Right-column ""    = max(top_right.w, bottom_right.w)
      A row/column whose quadrants are all unconnected contributes 0.
      Quadrants smaller than their cell are top-left aligned and padded
      with black on the right / bottom edges.

    Type strategy (promote to widest):
      If any connected input is colour (:data:`IoDataType.IMAGE`), every
      grayscale input is promoted to BGR via ``cv2.cvtColor(...,
      COLOR_GRAY2BGR)`` and the output is emitted as ``IMAGE``. If every
      connected input is :data:`IoDataType.IMAGE_GREY`, the output stays
      grayscale.
    """

    _QUADRANTS = ("top_left", "top_right", "bottom_left", "bottom_right")

    def __init__(self) -> None:
        super().__init__("Merge", section="Composit")
        for name in self._QUADRANTS:
            self._add_input(InputPort(name, set(IMAGE_TYPES)))
        self._add_output(OutputPort("image", set(IMAGE_TYPES)))

    # ── Parameters ─────────────────────────────────────────────────────────────

    @property
    @override
    def params(self) -> list[NodeParam]:
        return []

    # ── NodeBase interface ─────────────────────────────────────────────────────

    @override
    def _signal_input_ready(self) -> None:
        """Fire when every *connected* input has delivered data.

        Overrides the default (all-inputs-ready) because Merge deliberately
        supports partial connections — unconnected ports never receive
        anything, so waiting on them would deadlock the node.
        """
        connected = [p for p in self._inputs if p.upstream is not None]
        if not connected:
            return

        if all(p.has_data for p in connected):
            self.process()
            for p in connected:
                p.clear()
            return

        if all(p.finished for p in connected):
            self._on_finish()

    @override
    def process_impl(self) -> None:
        # Collect the IoData for every quadrant (None when unconnected).
        quads: list[IoData | None] = [
            p.data if p.has_data else None for p in self._inputs
        ]
        tl, tr, bl, br = quads

        # "Promote to colour" — if any input is colour, output is colour.
        any_color = any(
            q is not None and q.type == IoDataType.IMAGE for q in quads
        )

        def cell(q: IoData | None) -> np.ndarray | None:
            if q is None:
                return None
            img = q.image
            if any_color and q.type == IoDataType.IMAGE_GREY:
                return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
            return img

        tl_img, tr_img, bl_img, br_img = cell(tl), cell(tr), cell(bl), cell(br)

        def max_dim(imgs: tuple[np.ndarray | None, ...], axis: int) -> int:
            return max((img.shape[axis] for img in imgs if img is not None), default=0)

        top_h    = max_dim((tl_img, tr_img), 0)
        bottom_h = max_dim((bl_img, br_img), 0)
        left_w   = max_dim((tl_img, bl_img), 1)
        right_w  = max_dim((tr_img, br_img), 1)

        total_h = top_h + bottom_h
        total_w = left_w + right_w
        if total_h == 0 or total_w == 0:
            return  # nothing to emit — every connected quadrant was empty

        if any_color:
            canvas = np.zeros((total_h, total_w, 3), dtype=np.uint8)
        else:
            canvas = np.zeros((total_h, total_w), dtype=np.uint8)

        def paste(img: np.ndarray | None, y0: int, x0: int) -> None:
            if img is None:
                return
            h, w = img.shape[:2]
            canvas[y0:y0 + h, x0:x0 + w] = img

        paste(tl_img, 0,     0)
        paste(tr_img, 0,     left_w)
        paste(bl_img, top_h, 0)
        paste(br_img, top_h, left_w)

        if any_color:
            self.outputs[0].send(IoData.from_image(canvas))
        else:
            self.outputs[0].send(IoData.from_greyscale(canvas))

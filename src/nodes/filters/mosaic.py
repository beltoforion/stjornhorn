"""Mosaic — variable-layout image composer.

Single node that subsumes :class:`Merge` (2x2 grid) and
:class:`StackVertical` / :class:`StackHorizontal` (issue #223). The
layout is declared by a small descriptor string: rows are separated
by ``;``, cells inside a row by ``,``. Each cell is the 1-based
index of an ``image_i`` input.

Composition rules:
  * Inside a row, every image is scaled aspect-preserving to the
    common row height (= max input height in that row); widths
    follow naturally and the row is built by horizontal hstack.
  * After all rows are built, each row image is scaled
    aspect-preserving to the widest row's width, so its height
    grows / shrinks proportionally.
  * Rows are stacked vertically into the final canvas.

This produces no black bars: there is no fixed grid, no spanning,
no padding. Aspect ratios are preserved everywhere.

Inputs are a fixed pool of nine optional ``image_i`` ports. The
editor starts with a single visible row and grows by one row each
time the user wires up the previous tail (see
:attr:`NodeBase.SHOW_ONLY_USED_INPUTS`).
"""
from __future__ import annotations

import cv2
import numpy as np
from typing_extensions import override

from core.io_data import IMAGE_TYPES, IoData, IoDataType
from core.node_base import NodeBase
from core.params import StringParam
from core.port import InputPort, OutputPort

#: Total number of ``image_i`` input ports the node owns.
_NUM_INPUTS: int = 9

#: Row separator inside the layout descriptor.
_ROW_SEPARATOR: str = ";"

#: Cell separator inside a row.
_CELL_SEPARATOR: str = ","

#: Resampling filter used for the per-row height match and for the
#: final per-row width match. ``INTER_AREA`` gives clean downscales
#: and acceptable upscales without the speckle of ``INTER_NEAREST``;
#: it's the same trade-off the rest of the image filters in the
#: codebase pick for content-agnostic resizes.
_RESAMPLE: int = cv2.INTER_AREA


class MosaicLayout:
    """Parses a Mosaic layout descriptor.

    Syntax:
      * Rows are separated by ``;``.
      * Inside a row, cells are separated by ``,``.
      * Each cell is a 1-based integer that references the matching
        ``image_<n>`` input port.
      * Whitespace around any token is ignored.
      * A trailing ``;`` (or fully blank rows) is tolerated; an
        empty cell token (``"1,,2"`` or ``",1"``) is a parse error.

    Examples::

        "1,2"            two inputs side by side (was: "12")
        "1;2"            two inputs stacked vertically (was: "1/2")
        "1,2;3,4"        2x2 grid (was: "12/34")
        "1,2;3"          row 1 holds two images, row 2 holds one;
                         row 2 is then scaled to row 1's width
    """

    HEADER_ICON = "grid_view"

    def __init__(self, descriptor: str) -> None:
        self._descriptor = descriptor
        self._rows: list[list[int]] = self._parse(descriptor)

    @staticmethod
    def _parse(descriptor: str) -> list[list[int]]:
        rows: list[list[int]] = []
        for raw_row in descriptor.split(_ROW_SEPARATOR):
            if not raw_row.strip():
                continue  # trailing ';' or blank row → skip silently
            row: list[int] = []
            for raw_cell in raw_row.split(_CELL_SEPARATOR):
                token = raw_cell.strip()
                if not token:
                    raise ValueError(
                        f"Mosaic layout has an empty cell in row "
                        f"{raw_row!r}: {descriptor!r}"
                    )
                try:
                    n = int(token)
                except ValueError as exc:
                    raise ValueError(
                        f"Mosaic cell {token!r} is not an integer: "
                        f"{descriptor!r}"
                    ) from exc
                if n < 1:
                    raise ValueError(
                        f"Mosaic cell {n} must be 1-based (>=1): "
                        f"{descriptor!r}"
                    )
                row.append(n - 1)
            rows.append(row)
        if not rows:
            raise ValueError(f"Mosaic layout is empty: {descriptor!r}")
        return rows

    @property
    def rows(self) -> list[list[int]]:
        """Per-row lists of zero-based input port indices."""
        return [list(r) for r in self._rows]


class Mosaic(NodeBase):
    """Composite up to nine images into a flexible row/column layout.

    The ``layout`` descriptor is a list of rows separated by ``;``;
    inside a row, image-input indices are separated by ``,`` (1-based).
    Aspect ratios are preserved at every step:

      * Per row: every image is scaled to the row's common height
        (the max input height) and laid out left-to-right.
      * After all rows are built, each row is scaled to the widest
        row's width; the row's height grows / shrinks proportionally.
      * Rows are stacked vertically into the output image.

    Any colour input promotes the output to colour; otherwise the
    output stays greyscale. The default ``"1,2"`` is a horizontal
    pair of the first two inputs.
    """

    SHOW_ONLY_USED_INPUTS: bool = True

    layout = StringParam(
        "1,2",
        placeholder="1,2",
        constant=True,
        description=(
            "Layout descriptor. Rows separated by ';', cells inside "
            "a row separated by ','. Each cell is the 1-based index "
            "of an image_<n> input. Examples: '1,2', '1;2', "
            "'1,2;3,4', '1,2;3'."
        ),
    )

    def __init__(self) -> None:
        super().__init__("Mosaic", section="Composit")
        self._layout: str
        for i in range(1, _NUM_INPUTS + 1):
            self._add_input(InputPort(
                f"image_{i}", set(IMAGE_TYPES), optional=True,
            ))
        self._add_output(OutputPort("image", set(IMAGE_TYPES)))
        self._apply_default_params()

    @override
    def process_impl(self) -> None:
        layout = MosaicLayout(self._layout)
        ports = self.inputs

        # Gather IoData per row, dropping cells whose referenced
        # port is out of range or has no data. A row that ends up
        # entirely empty is dropped from the output.
        rows_data: list[list[IoData]] = []
        for row in layout.rows:
            row_data: list[IoData] = []
            for idx in row:
                if idx >= len(ports):
                    continue
                port = ports[idx]
                if port.has_data:
                    row_data.append(port.data)
            if row_data:
                rows_data.append(row_data)

        if not rows_data:
            return

        any_color = any(
            d.type == IoDataType.IMAGE
            for row in rows_data for d in row
        )

        row_imgs = [self._build_row(row, any_color) for row in rows_data]
        target_w = max(img.shape[1] for img in row_imgs)
        scaled = [self._scale_to_width(img, target_w) for img in row_imgs]
        canvas = np.vstack(scaled)

        # Forward meta from the first non-empty cell of the first row.
        # In typical use every cell traces back to the same upstream
        # frame (e.g. the bulk-FFT flow runs an image through
        # HsvSplit → Fft2D → ApplyColormap and feeds the result back
        # into Mosaic alongside the original); picking the first cell
        # is a deterministic choice that preserves source_path /
        # frame_index without trying to reconcile divergent metas.
        head_meta = rows_data[0][0].meta
        if any_color:
            self.outputs[0].send(IoData.from_image(canvas, meta=head_meta))
        else:
            self.outputs[0].send(IoData.from_greyscale(canvas, meta=head_meta))

    @classmethod
    def _build_row(
        cls, row: list[IoData], any_color: bool,
    ) -> np.ndarray:
        """Assemble one row by aspect-preserving height match + hstack."""
        imgs = [cls._promote(d, any_color) for d in row]
        target_h = max(im.shape[0] for im in imgs)
        scaled = [cls._scale_to_height(im, target_h) for im in imgs]
        return np.hstack(scaled)

    @staticmethod
    def _promote(data: IoData, to_color: bool) -> np.ndarray:
        img = data.image
        if to_color:
            if data.type == IoDataType.IMAGE_GREY:
                return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
            if img.ndim == 3 and img.shape[2] == 4:
                return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        return img

    @staticmethod
    def _scale_to_height(img: np.ndarray, target_h: int) -> np.ndarray:
        h, w = img.shape[:2]
        if h == target_h:
            return img
        new_w = max(1, round(w * target_h / h))
        return cv2.resize(img, (new_w, target_h), interpolation=_RESAMPLE)

    @staticmethod
    def _scale_to_width(img: np.ndarray, target_w: int) -> np.ndarray:
        h, w = img.shape[:2]
        if w == target_w:
            return img
        new_h = max(1, round(h * target_w / w))
        return cv2.resize(img, (target_w, new_h), interpolation=_RESAMPLE)

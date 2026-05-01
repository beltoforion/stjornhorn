"""Mosaic — variable-layout image composer.

Single node that subsumes :class:`Merge` (2x2 grid) and
:class:`StackVertical` / :class:`StackHorizontal` (issue #223). The
layout is declared by a small descriptor string so a single Mosaic
can express side-by-side stacks, NxM grids, and shapes where one
input spans multiple cells (e.g. a tall hodogram next to two stacked
waveforms).

Inputs are a fixed pool of nine optional ``image_i`` ports. The
editor starts with a single visible row and grows by one row each
time the user wires up the previous tail (see
:attr:`NodeBase.SHOW_ONLY_USED_INPUTS`). Layout cells reference
inputs by digit (``1``…``9``); ``image_i`` is referenced as ``i``
in the descriptor string.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from typing_extensions import override

from core.io_data import IMAGE_TYPES, IoData, IoDataType
from core.node_base import NodeBase
from core.params import StringParam
from core.port import InputPort, OutputPort

#: Total number of ``image_i`` input ports the node owns.
_NUM_INPUTS: int = 9

#: Digits that may appear in a layout cell. Each digit ``d``
#: references input port ``image_<d>`` (1-indexed).
_LAYOUT_DIGITS: str = "123456789"

#: Markers for an empty cell in the layout string. Both ``.`` and
#: ``0`` work — ``0`` keeps a fixed-width grid easy to read at a
#: glance (every cell is exactly one character with no symbol soup).
_EMPTY_CELLS: frozenset[str] = frozenset({".", "0"})

#: Row separator inside the layout string.
_ROW_SEPARATOR: str = "/"


@dataclass(frozen=True)
class _Rect:
    """Inclusive cell bounds for one input within the layout grid."""

    digit: str
    top: int
    bottom: int
    left: int
    right: int

    @property
    def row_span(self) -> int:
        return self.bottom - self.top + 1

    @property
    def col_span(self) -> int:
        return self.right - self.left + 1

    @property
    def port_index(self) -> int:
        """Zero-based index of the input port this rectangle refers to.

        ``self.digit`` is the user-facing 1-based label that appears in
        the layout descriptor; the framework's port list is 0-indexed.
        """
        return int(self.digit) - 1


class MosaicLayout:
    """Parses and validates a layout descriptor string.

    Syntax:
      * Rows are separated by ``/``.
      * Inside a row, every non-whitespace character is one cell:
        a digit ``1``–``9`` (referencing input port ``image_<d>``),
        or ``.`` / ``0`` for an empty cell.
      * A digit that occupies multiple adjacent cells declares a
        spanning input — those cells must form an axis-aligned
        rectangle (no holes, no L-shapes within a single digit).
      * Every row must have the same column count.

    Examples::

        "12"              two inputs side by side
        "1 / 2"           two inputs stacked vertically
        "12 / 34"         classic 2x2 grid
        "13 / 23"         image_1 and image_2 on the left,
                          image_3 spans two rows on the right
        "11 / 2."         image_1 spans the top row, image_2
                          only bottom-left

    Whitespace inside a row is ignored, so ``"1 2 / 3 4"`` and
    ``"12 / 34"`` parse the same.
    """

    def __init__(self, descriptor: str) -> None:
        self._descriptor = descriptor
        self._rows: list[str] = self._parse_rows(descriptor)
        self._n_rows: int = len(self._rows)
        self._n_cols: int = len(self._rows[0])
        self._rects: list[_Rect] = self._parse_rectangles()

    @staticmethod
    def _parse_rows(descriptor: str) -> list[str]:
        raw_rows = [r.replace(" ", "").replace("\t", "")
                    for r in descriptor.split(_ROW_SEPARATOR)]
        rows = [r for r in raw_rows if r]
        if not rows:
            raise ValueError("Mosaic layout is empty")
        n_cols = len(rows[0])
        for i, r in enumerate(rows):
            if len(r) != n_cols:
                raise ValueError(
                    f"Mosaic row {i} has {len(r)} cells, expected {n_cols}: "
                    f"{descriptor!r}"
                )
            for ch in r:
                if ch in _EMPTY_CELLS:
                    continue
                if ch not in _LAYOUT_DIGITS:
                    raise ValueError(
                        f"Mosaic cell {ch!r} is not a digit 1-9 or empty "
                        f"({sorted(_EMPTY_CELLS)}): {descriptor!r}"
                    )
        return rows

    def _parse_rectangles(self) -> list[_Rect]:
        seen_digits: dict[str, list[tuple[int, int]]] = {}
        for i, row in enumerate(self._rows):
            for j, ch in enumerate(row):
                if ch in _EMPTY_CELLS:
                    continue
                seen_digits.setdefault(ch, []).append((i, j))

        rects: list[_Rect] = []
        for digit, cells in seen_digits.items():
            top = min(i for i, _ in cells)
            bottom = max(i for i, _ in cells)
            left = min(j for _, j in cells)
            right = max(j for _, j in cells)
            expected = {(i, j)
                        for i in range(top, bottom + 1)
                        for j in range(left, right + 1)}
            if set(cells) != expected:
                raise ValueError(
                    f"Mosaic digit {digit!r} does not form a rectangle "
                    f"in layout {self._descriptor!r}"
                )
            rects.append(_Rect(digit, top, bottom, left, right))
        return rects

    @property
    def rows(self) -> int:
        return self._n_rows

    @property
    def cols(self) -> int:
        return self._n_cols

    @property
    def rectangles(self) -> list[_Rect]:
        return list(self._rects)


class Mosaic(NodeBase):
    """Composite up to nine images into a flexible grid layout.

    The ``layout`` string describes the cell arrangement (see
    :class:`MosaicLayout` for syntax). Digits ``1``–``9`` map to the
    nine optional inputs ``image_1``…``image_9`` in order; ``.`` or
    ``0`` and unconnected cells are black padding. Each input is
    pasted at the top-left of its cell rectangle and padded on the
    right / bottom if smaller.

    Inputs are a fixed pool of nine optional ``image_i`` ports. The
    editor starts with a single visible row and grows by one row each
    time the user wires up the previous tail. The layout descriptor
    is a constant parameter (rendered italicised between the output
    and input rows) — its digits index into the input list
    independently of how many ports are currently visible on the node.

    Any colour input promotes the output to colour; otherwise the
    output stays greyscale. The default ``"12"`` is a horizontal
    stack of the first two inputs.
    """

    SHOW_ONLY_USED_INPUTS: bool = True

    layout = StringParam(
        "12",
        placeholder="12",
        constant=True,
        description=(
            "Layout descriptor. Rows separated by '/', each digit "
            "(1-9) references the matching image_<digit> input, '.' or "
            "'0' is empty. Repeat a digit across adjacent cells to "
            "span a rectangle. Examples: '12', '1 / 2', '12 / 34', "
            "'13 / 23'."
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

        # Map each rectangle to its IoData (skip rectangles whose
        # referenced port has no data — unconnected, or out of range).
        rect_data: dict[_Rect, IoData] = {}
        for rect in layout.rectangles:
            idx = rect.port_index
            if idx >= len(ports):
                continue
            port = ports[idx]
            if port.has_data:
                rect_data[rect] = port.data

        if not rect_data:
            return  # nothing to emit — every referenced cell was empty

        any_color = any(d.type == IoDataType.IMAGE for d in rect_data.values())

        # Pre-promote greyscale → BGR if mixing channel counts.
        rect_imgs: dict[_Rect, np.ndarray] = {}
        for rect, data in rect_data.items():
            img = data.image
            if any_color and data.type == IoDataType.IMAGE_GREY:
                img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
            rect_imgs[rect] = img

        col_widths = self._solve_track_sizes(
            rect_imgs, layout.cols, axis="col"
        )
        row_heights = self._solve_track_sizes(
            rect_imgs, layout.rows, axis="row"
        )

        total_w = sum(col_widths)
        total_h = sum(row_heights)
        if total_w == 0 or total_h == 0:
            return

        if any_color:
            canvas = np.zeros((total_h, total_w, 3), dtype=np.uint8)
        else:
            canvas = np.zeros((total_h, total_w), dtype=np.uint8)

        col_starts = self._cumulative_starts(col_widths)
        row_starts = self._cumulative_starts(row_heights)

        for rect, img in rect_imgs.items():
            y0 = row_starts[rect.top]
            x0 = col_starts[rect.left]
            h, w = img.shape[:2]
            canvas[y0:y0 + h, x0:x0 + w] = img

        if any_color:
            self.outputs[0].send(IoData.from_image(canvas))
        else:
            self.outputs[0].send(IoData.from_greyscale(canvas))

    @staticmethod
    def _solve_track_sizes(
        rect_imgs: dict[_Rect, np.ndarray], n_tracks: int, *, axis: str,
    ) -> list[int]:
        """Compute per-row or per-column sizes.

        Each track's size is ``max(input_extent / span)`` over every
        input whose rectangle includes that track. Spanning inputs
        contribute their averaged dimension so a tall rectangle's
        budget is split evenly across the rows it covers.
        """
        sizes = [0] * n_tracks
        for rect, img in rect_imgs.items():
            if axis == "col":
                extent = img.shape[1]
                span = rect.col_span
                start, stop = rect.left, rect.right
            else:
                extent = img.shape[0]
                span = rect.row_span
                start, stop = rect.top, rect.bottom
            per_track = (extent + span - 1) // span  # ceil so spans cover input
            for t in range(start, stop + 1):
                if per_track > sizes[t]:
                    sizes[t] = per_track
        return sizes

    @staticmethod
    def _cumulative_starts(sizes: list[int]) -> list[int]:
        starts = [0] * len(sizes)
        running = 0
        for i, s in enumerate(sizes):
            starts[i] = running
            running += s
        return starts

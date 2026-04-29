"""Mosaic — variable-layout image composer.

Single node that subsumes :class:`Merge` (2x2 grid) and
:class:`StackVertical` / :class:`StackHorizontal` (issue #223). The
layout is declared by a small descriptor string so a single Mosaic
can express side-by-side stacks, NxM grids, and shapes where one
input spans multiple cells (e.g. a tall hodogram next to two stacked
waveforms).
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

#: Number of optional IMAGE inputs the node exposes. Letters ``A``…
#: ``F`` of the layout string map to ports 0…5. Six is enough for a
#: 2x3 / 3x2 grid (the largest the existing flows need) plus a couple
#: of slots for spanning shapes.
_NUM_INPUTS: int = 6
_INPUT_LETTERS: str = "ABCDEF"

#: Marker for an empty cell in the layout string.
_EMPTY_CELL: str = "."

#: Row separator inside the layout string.
_ROW_SEPARATOR: str = "/"


@dataclass(frozen=True)
class _Rect:
    """Inclusive cell bounds for one input within the layout grid."""

    letter: str
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


class MosaicLayout:
    """Parses and validates a layout descriptor string.

    Syntax:
      * Rows are separated by ``/``.
      * Inside a row, every non-whitespace character is one cell:
        an uppercase letter ``A``–``F`` (mapped to input port 0–5),
        or ``.`` for an empty cell.
      * A letter that occupies multiple adjacent cells declares a
        spanning input — those cells must form an axis-aligned
        rectangle (no holes, no L-shapes within a single letter).
      * Every row must have the same column count.

    Examples::

        "AB"              two inputs side by side
        "A / B"           two inputs stacked vertically
        "AB / CD"         classic 2x2 grid
        "AC / BC"         A and B on the left, C spans two rows on the right
        "AA / B."         A spans the top row, B only bottom-left

    Whitespace inside a row is ignored, so ``"A B / C D"`` and
    ``"AB / CD"`` parse the same.
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
                if ch == _EMPTY_CELL:
                    continue
                if not (ch.isalpha() and ch.isupper()):
                    raise ValueError(
                        f"Mosaic cell {ch!r} is not an uppercase letter "
                        f"or {_EMPTY_CELL!r}: {descriptor!r}"
                    )
        return rows

    def _parse_rectangles(self) -> list[_Rect]:
        seen_letters: dict[str, list[tuple[int, int]]] = {}
        for i, row in enumerate(self._rows):
            for j, ch in enumerate(row):
                if ch == _EMPTY_CELL:
                    continue
                seen_letters.setdefault(ch, []).append((i, j))

        rects: list[_Rect] = []
        for letter, cells in seen_letters.items():
            top = min(i for i, _ in cells)
            bottom = max(i for i, _ in cells)
            left = min(j for _, j in cells)
            right = max(j for _, j in cells)
            expected = {(i, j)
                        for i in range(top, bottom + 1)
                        for j in range(left, right + 1)}
            if set(cells) != expected:
                raise ValueError(
                    f"Mosaic letter {letter!r} does not form a rectangle "
                    f"in layout {self._descriptor!r}"
                )
            rects.append(_Rect(letter, top, bottom, left, right))
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
    """Composite up to six images into a flexible grid layout.

    A single ``layout`` string describes the cell arrangement (see
    :class:`MosaicLayout` for syntax). Each letter ``A``–``F`` maps
    to one of the six optional ``IMAGE`` inputs in order. Cells with
    no incoming data — either because their input is unconnected or
    because the layout uses ``.`` — are left as black padding.

    Sizing strategy:
      * ``col_width[j] = max(input.width / col_span)`` over every
        input whose rectangle includes column ``j``. Row heights are
        the symmetric per-row max. Inputs spanning multiple cells
        contribute their averaged dimension so the cell budget stays
        proportional.
      * Each input is pasted at the top-left of its rectangle and
        padded on the right / bottom if smaller than the rectangle.

    Type strategy (matches :class:`Merge`):
      * Any colour input → output is colour; greyscale inputs are
        promoted via ``cv2.cvtColor(..., COLOR_GRAY2BGR)``.
      * All-greyscale inputs → output stays greyscale.

    The default layout ``"AB"`` produces a horizontal stack of the
    first two inputs, matching the most common simple use.
    """

    layout = StringParam(
        "AB",
        placeholder="AB",
        description=(
            "Layout descriptor. Rows separated by '/', each letter "
            "(A-F) is one cell, '.' is empty. Repeat a letter across "
            "adjacent cells to span a rectangle. Examples: 'AB', "
            "'A / B', 'AB / CD', 'AC / BC'."
        ),
    )

    def __init__(self) -> None:
        super().__init__("Mosaic", section="Composit")
        self._layout: str
        for letter in _INPUT_LETTERS:
            self._add_input(InputPort(letter, set(IMAGE_TYPES), optional=True))
        self._add_output(OutputPort("image", set(IMAGE_TYPES)))
        self._apply_default_params()

    @override
    def process_impl(self) -> None:
        layout = MosaicLayout(self._layout)

        # Map each rectangle to its IoData (None if input is empty / unconnected).
        rect_data: dict[_Rect, IoData] = {}
        for rect in layout.rectangles:
            idx = _INPUT_LETTERS.index(rect.letter)
            port = self._inputs[idx]
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

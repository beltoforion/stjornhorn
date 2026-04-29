"""Tests for the :class:`~nodes.filters.mosaic.Mosaic` node and its
layout descriptor parser :class:`MosaicLayout`."""
from __future__ import annotations

import numpy as np
import pytest

from core.io_data import IoData, IoDataType
from core.port import OutputPort
from nodes.filters.mosaic import Mosaic, MosaicLayout


# ── Layout descriptor parser ──────────────────────────────────────────────────


def test_layout_horizontal_pair() -> None:
    layout = MosaicLayout("AB")
    assert (layout.rows, layout.cols) == (1, 2)
    rects = {r.letter: r for r in layout.rectangles}
    assert rects["A"].col_span == 1 and rects["A"].row_span == 1
    assert rects["B"].left == 1


def test_layout_vertical_pair() -> None:
    layout = MosaicLayout("A / B")
    assert (layout.rows, layout.cols) == (2, 1)
    rects = {r.letter: r for r in layout.rectangles}
    assert rects["B"].top == 1


def test_layout_2x2_grid() -> None:
    layout = MosaicLayout("AB / CD")
    assert (layout.rows, layout.cols) == (2, 2)
    assert {r.letter for r in layout.rectangles} == {"A", "B", "C", "D"}


def test_layout_l_shape_with_span() -> None:
    """``"AC / BC"`` — A and B on the left, C spans two rows on right."""
    layout = MosaicLayout("AC / BC")
    rects = {r.letter: r for r in layout.rectangles}
    assert rects["C"].row_span == 2
    assert rects["C"].col_span == 1
    assert rects["A"].row_span == 1


def test_layout_empty_cell_with_dot() -> None:
    layout = MosaicLayout("AB / .B")
    rects = {r.letter: r for r in layout.rectangles}
    assert "A" in rects and "B" in rects
    assert rects["B"].row_span == 2


def test_layout_whitespace_inside_row_is_ignored() -> None:
    a = MosaicLayout("A B / C D")
    b = MosaicLayout("AB / CD")
    assert (a.rows, a.cols) == (b.rows, b.cols)
    assert {r.letter for r in a.rectangles} == {r.letter for r in b.rectangles}


def test_layout_rejects_non_rectangle() -> None:
    """``"AB / BA"`` — letter A appears at (0,0) and (1,1), not a rectangle."""
    with pytest.raises(ValueError, match="does not form a rectangle"):
        MosaicLayout("AB / BA")


def test_layout_rejects_uneven_rows() -> None:
    with pytest.raises(ValueError, match="cells, expected"):
        MosaicLayout("AB / CDE")


def test_layout_rejects_invalid_character() -> None:
    with pytest.raises(ValueError, match="not an uppercase letter"):
        MosaicLayout("Ab")


def test_layout_rejects_empty_descriptor() -> None:
    with pytest.raises(ValueError, match="empty"):
        MosaicLayout("")


# ── Mosaic node — render output ───────────────────────────────────────────────


def _bgr(h: int, w: int, value: int) -> np.ndarray:
    return np.full((h, w, 3), value, dtype=np.uint8)


def _grey(h: int, w: int, value: int) -> np.ndarray:
    return np.full((h, w), value, dtype=np.uint8)


def _wire(node: Mosaic, letter_to_data: dict[str, IoData]) -> None:
    """Connect a fake upstream per used letter, then send all the data.

    Mosaic only fires once every connected input has data, so every
    upstream must be connected before any send() runs.
    """
    upstreams: list[tuple[OutputPort, IoData]] = []
    for letter, data in letter_to_data.items():
        idx = "ABCDEF".index(letter)
        up = OutputPort(letter, {data.type})
        up.connect(node.inputs[idx])
        upstreams.append((up, data))
    for up, data in upstreams:
        up.send(data)


def test_mosaic_default_layout_is_horizontal_pair() -> None:
    node = Mosaic()
    _wire(node, {
        "A": IoData.from_image(_bgr(4, 6, 10)),
        "B": IoData.from_image(_bgr(4, 6, 20)),
    })
    out = node.outputs[0].last_emitted
    assert out is not None
    assert out.image.shape == (4, 12, 3)
    assert out.image[0, 0, 0] == 10
    assert out.image[0, 6, 0] == 20


def test_mosaic_vertical_stack() -> None:
    node = Mosaic()
    node.layout = "A / B"
    _wire(node, {
        "A": IoData.from_image(_bgr(4, 6, 10)),
        "B": IoData.from_image(_bgr(4, 6, 20)),
    })
    out = node.outputs[0].last_emitted
    assert out is not None
    assert out.image.shape == (8, 6, 3)
    assert out.image[0, 0, 0] == 10
    assert out.image[4, 0, 0] == 20


def test_mosaic_2x2_grid_color_inputs() -> None:
    """Replaces the canonical Merge 2x2 use case."""
    node = Mosaic()
    node.layout = "AB / CD"
    _wire(node, {
        "A": IoData.from_image(_bgr(4, 6, 10)),
        "B": IoData.from_image(_bgr(4, 6, 20)),
        "C": IoData.from_image(_bgr(4, 6, 30)),
        "D": IoData.from_image(_bgr(4, 6, 40)),
    })
    out = node.outputs[0].last_emitted
    assert out is not None
    assert out.image.shape == (8, 12, 3)
    assert out.image[0, 0, 0] == 10
    assert out.image[0, 6, 0] == 20
    assert out.image[4, 0, 0] == 30
    assert out.image[4, 6, 0] == 40


def test_mosaic_l_shape_with_spanning_input() -> None:
    """``"AC / BC"`` — A and B on left (1600x400 each), C spans both
    rows on the right (800x800). The seismic demo flow's actual shape."""
    node = Mosaic()
    node.layout = "AC / BC"
    _wire(node, {
        "A": IoData.from_image(_bgr(400, 1600, 10)),
        "B": IoData.from_image(_bgr(400, 1600, 20)),
        "C": IoData.from_image(_bgr(800, 800, 30)),
    })
    out = node.outputs[0].last_emitted
    assert out is not None
    assert out.image.shape == (800, 2400, 3)
    # A at (0,0), B at (400,0), C at (0,1600).
    assert out.image[0, 0, 0] == 10
    assert out.image[400, 0, 0] == 20
    assert out.image[0, 1600, 0] == 30
    assert out.image[799, 1600, 0] == 30  # C fills the full right column


def test_mosaic_all_greyscale_inputs_emit_greyscale() -> None:
    node = Mosaic()
    node.layout = "AB / CD"
    _wire(node, {
        "A": IoData.from_greyscale(_grey(3, 5, 10)),
        "B": IoData.from_greyscale(_grey(3, 5, 20)),
        "C": IoData.from_greyscale(_grey(3, 5, 30)),
        "D": IoData.from_greyscale(_grey(3, 5, 40)),
    })
    out = node.outputs[0].last_emitted
    assert out is not None
    assert out.type == IoDataType.IMAGE_GREY
    assert out.image.shape == (6, 10)


def test_mosaic_mixed_types_promote_to_color() -> None:
    node = Mosaic()
    node.layout = "AB"
    _wire(node, {
        "A": IoData.from_greyscale(_grey(2, 2, 77)),
        "B": IoData.from_image(_bgr(2, 2, 200)),
    })
    out = node.outputs[0].last_emitted
    assert out is not None
    assert out.type == IoDataType.IMAGE
    np.testing.assert_array_equal(out.image[0:2, 0:2], _bgr(2, 2, 77))
    np.testing.assert_array_equal(out.image[0:2, 2:4], _bgr(2, 2, 200))


def test_mosaic_unconnected_letter_renders_as_black_padding() -> None:
    """Layout ``"AB / CD"`` but only A and D wired — B and C cells stay zero."""
    node = Mosaic()
    node.layout = "AB / CD"
    _wire(node, {
        "A": IoData.from_image(_bgr(4, 5, 111)),
        "D": IoData.from_image(_bgr(6, 7, 222)),
    })
    out = node.outputs[0].last_emitted
    assert out is not None
    assert out.image.shape == (10, 12, 3)
    np.testing.assert_array_equal(out.image[0:4, 0:5], _bgr(4, 5, 111))
    np.testing.assert_array_equal(out.image[4:10, 5:12], _bgr(6, 7, 222))
    # Missing B cell (rows 0:4, cols 5:12) is black; same for C.
    assert out.image[0:4, 5:12].sum() == 0
    assert out.image[4:10, 0:5].sum() == 0


def test_mosaic_explicit_dot_cell_is_black_padding() -> None:
    """Layout ``"AB / .B"`` — bottom-left explicitly empty; B spans rows."""
    node = Mosaic()
    node.layout = "AB / .B"
    _wire(node, {
        "A": IoData.from_image(_bgr(4, 5, 100)),
        "B": IoData.from_image(_bgr(8, 6, 200)),
    })
    out = node.outputs[0].last_emitted
    assert out is not None
    # row_height: row 0 = max(4, 8/2=4) = 4; row 1 = max(8/2=4) = 4. Total 8.
    # col_width:  col 0 = max(5) = 5; col 1 = max(6) = 6. Total 11.
    assert out.image.shape == (8, 11, 3)
    np.testing.assert_array_equal(out.image[0:4, 0:5], _bgr(4, 5, 100))
    # Bottom-left cell stays black.
    assert out.image[4:8, 0:5].sum() == 0


def test_mosaic_does_not_fire_until_every_connected_input_has_data() -> None:
    """Same wiring contract as Merge: connected upstreams gate the dispatch."""
    node = Mosaic()
    node.layout = "AB / CD"
    up_a = OutputPort("A", {IoDataType.IMAGE})
    up_b = OutputPort("B", {IoDataType.IMAGE})
    up_c = OutputPort("C", {IoDataType.IMAGE})
    up_a.connect(node.inputs[0])
    up_b.connect(node.inputs[1])
    up_c.connect(node.inputs[2])

    up_a.send(IoData.from_image(_bgr(2, 2, 1)))
    up_b.send(IoData.from_image(_bgr(2, 2, 2)))
    assert node.outputs[0].last_emitted is None

    up_c.send(IoData.from_image(_bgr(2, 2, 3)))
    assert node.outputs[0].last_emitted is not None


def test_mosaic_invalid_layout_raises_at_process_time() -> None:
    node = Mosaic()
    node.layout = "AB / BA"
    with pytest.raises(ValueError, match="rectangle"):
        _wire(node, {
            "A": IoData.from_image(_bgr(2, 2, 10)),
            "B": IoData.from_image(_bgr(2, 2, 20)),
        })

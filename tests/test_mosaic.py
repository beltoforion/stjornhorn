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
    layout = MosaicLayout("12")
    assert (layout.rows, layout.cols) == (1, 2)
    rects = {r.digit: r for r in layout.rectangles}
    assert rects["1"].col_span == 1 and rects["1"].row_span == 1
    assert rects["2"].left == 1


def test_layout_vertical_pair() -> None:
    layout = MosaicLayout("1 / 2")
    assert (layout.rows, layout.cols) == (2, 1)
    rects = {r.digit: r for r in layout.rectangles}
    assert rects["2"].top == 1


def test_layout_2x2_grid() -> None:
    layout = MosaicLayout("12 / 34")
    assert (layout.rows, layout.cols) == (2, 2)
    assert {r.digit for r in layout.rectangles} == {"1", "2", "3", "4"}


def test_layout_l_shape_with_span() -> None:
    """``"13 / 23"`` — 1 and 2 on the left, 3 spans two rows on right."""
    layout = MosaicLayout("13 / 23")
    rects = {r.digit: r for r in layout.rectangles}
    assert rects["3"].row_span == 2
    assert rects["3"].col_span == 1
    assert rects["1"].row_span == 1


def test_layout_empty_cell_with_dot() -> None:
    layout = MosaicLayout("12 / .2")
    rects = {r.digit: r for r in layout.rectangles}
    assert "1" in rects and "2" in rects
    assert rects["2"].row_span == 2


def test_layout_empty_cell_with_zero() -> None:
    """``0`` is also accepted as an empty-cell marker so a numeric
    layout reads cleanly without a stray ``.`` character."""
    layout = MosaicLayout("12 / 02")
    rects = {r.digit: r for r in layout.rectangles}
    assert rects["2"].row_span == 2


def test_layout_whitespace_inside_row_is_ignored() -> None:
    a = MosaicLayout("1 2 / 3 4")
    b = MosaicLayout("12 / 34")
    assert (a.rows, a.cols) == (b.rows, b.cols)
    assert {r.digit for r in a.rectangles} == {r.digit for r in b.rectangles}


def test_layout_rejects_non_rectangle() -> None:
    """``"12 / 21"`` — digit 1 appears at (0,0) and (1,1), not a rectangle."""
    with pytest.raises(ValueError, match="does not form a rectangle"):
        MosaicLayout("12 / 21")


def test_layout_rejects_uneven_rows() -> None:
    with pytest.raises(ValueError, match="cells, expected"):
        MosaicLayout("12 / 345")


def test_layout_rejects_invalid_character() -> None:
    with pytest.raises(ValueError, match="not a digit"):
        MosaicLayout("1A")


def test_layout_rejects_empty_descriptor() -> None:
    with pytest.raises(ValueError, match="empty"):
        MosaicLayout("")


# ── Topology ──────────────────────────────────────────────────────────────────


def test_has_nine_input_ports() -> None:
    """Backend always carries the full pool of nine ``image_i``
    ports; the editor hides the trailing unused rows."""
    node = Mosaic()
    assert [p.name for p in node.inputs] == [f"image_{i}" for i in range(1, 10)]


def test_show_only_used_inputs_is_set() -> None:
    assert Mosaic.SHOW_ONLY_USED_INPUTS is True


# ── Mosaic node — render output ───────────────────────────────────────────────


def _bgr(h: int, w: int, value: int) -> np.ndarray:
    return np.full((h, w, 3), value, dtype=np.uint8)


def _grey(h: int, w: int, value: int) -> np.ndarray:
    return np.full((h, w), value, dtype=np.uint8)


def _wire(node: Mosaic, digit_to_data: dict[str, IoData]) -> None:
    """Connect a fake upstream per used digit, then send all the data.

    Mosaic only fires once every connected input has data, so every
    upstream must be connected before any send() runs.
    """
    upstreams: list[tuple[OutputPort, IoData]] = []
    for digit, data in digit_to_data.items():
        idx = int(digit) - 1
        up = OutputPort(digit, {data.type})
        up.connect(node.inputs[idx])
        upstreams.append((up, data))
    for up, data in upstreams:
        up.send(data)


def test_mosaic_default_layout_is_horizontal_pair() -> None:
    node = Mosaic()
    _wire(node, {
        "1": IoData.from_image(_bgr(4, 6, 10)),
        "2": IoData.from_image(_bgr(4, 6, 20)),
    })
    out = node.outputs[0].last_emitted
    assert out is not None
    assert out.image.shape == (4, 12, 3)
    assert out.image[0, 0, 0] == 10
    assert out.image[0, 6, 0] == 20


def test_mosaic_vertical_stack() -> None:
    node = Mosaic()
    node.layout = "1 / 2"
    _wire(node, {
        "1": IoData.from_image(_bgr(4, 6, 10)),
        "2": IoData.from_image(_bgr(4, 6, 20)),
    })
    out = node.outputs[0].last_emitted
    assert out is not None
    assert out.image.shape == (8, 6, 3)
    assert out.image[0, 0, 0] == 10
    assert out.image[4, 0, 0] == 20


def test_mosaic_2x2_grid_color_inputs() -> None:
    """Replaces the canonical Merge 2x2 use case."""
    node = Mosaic()
    node.layout = "12 / 34"
    _wire(node, {
        "1": IoData.from_image(_bgr(4, 6, 10)),
        "2": IoData.from_image(_bgr(4, 6, 20)),
        "3": IoData.from_image(_bgr(4, 6, 30)),
        "4": IoData.from_image(_bgr(4, 6, 40)),
    })
    out = node.outputs[0].last_emitted
    assert out is not None
    assert out.image.shape == (8, 12, 3)
    assert out.image[0, 0, 0] == 10
    assert out.image[0, 6, 0] == 20
    assert out.image[4, 0, 0] == 30
    assert out.image[4, 6, 0] == 40


def test_mosaic_l_shape_with_spanning_input() -> None:
    """``"13 / 23"`` — image_1 / image_2 on left (1600x400 each),
    image_3 spans both rows on the right (800x800)."""
    node = Mosaic()
    node.layout = "13 / 23"
    _wire(node, {
        "1": IoData.from_image(_bgr(400, 1600, 10)),
        "2": IoData.from_image(_bgr(400, 1600, 20)),
        "3": IoData.from_image(_bgr(800, 800, 30)),
    })
    out = node.outputs[0].last_emitted
    assert out is not None
    assert out.image.shape == (800, 2400, 3)
    assert out.image[0, 0, 0] == 10
    assert out.image[400, 0, 0] == 20
    assert out.image[0, 1600, 0] == 30
    assert out.image[799, 1600, 0] == 30


def test_mosaic_all_greyscale_inputs_emit_greyscale() -> None:
    node = Mosaic()
    node.layout = "12 / 34"
    _wire(node, {
        "1": IoData.from_greyscale(_grey(3, 5, 10)),
        "2": IoData.from_greyscale(_grey(3, 5, 20)),
        "3": IoData.from_greyscale(_grey(3, 5, 30)),
        "4": IoData.from_greyscale(_grey(3, 5, 40)),
    })
    out = node.outputs[0].last_emitted
    assert out is not None
    assert out.type == IoDataType.IMAGE_GREY
    assert out.image.shape == (6, 10)


def test_mosaic_mixed_types_promote_to_color() -> None:
    node = Mosaic()
    node.layout = "12"
    _wire(node, {
        "1": IoData.from_greyscale(_grey(2, 2, 77)),
        "2": IoData.from_image(_bgr(2, 2, 200)),
    })
    out = node.outputs[0].last_emitted
    assert out is not None
    assert out.type == IoDataType.IMAGE
    np.testing.assert_array_equal(out.image[0:2, 0:2], _bgr(2, 2, 77))
    np.testing.assert_array_equal(out.image[0:2, 2:4], _bgr(2, 2, 200))


def test_mosaic_unconnected_digit_renders_as_black_padding() -> None:
    """Layout ``"12 / 34"`` but only image_1 and image_4 wired —
    image_2 and image_3 cells stay zero."""
    node = Mosaic()
    node.layout = "12 / 34"
    _wire(node, {
        "1": IoData.from_image(_bgr(4, 5, 111)),
        "4": IoData.from_image(_bgr(6, 7, 222)),
    })
    out = node.outputs[0].last_emitted
    assert out is not None
    assert out.image.shape == (10, 12, 3)
    np.testing.assert_array_equal(out.image[0:4, 0:5], _bgr(4, 5, 111))
    np.testing.assert_array_equal(out.image[4:10, 5:12], _bgr(6, 7, 222))
    assert out.image[0:4, 5:12].sum() == 0
    assert out.image[4:10, 0:5].sum() == 0


def test_mosaic_explicit_dot_cell_is_black_padding() -> None:
    """Layout ``"12 / .2"`` — bottom-left explicitly empty; image_2 spans rows."""
    node = Mosaic()
    node.layout = "12 / .2"
    _wire(node, {
        "1": IoData.from_image(_bgr(4, 5, 100)),
        "2": IoData.from_image(_bgr(8, 6, 200)),
    })
    out = node.outputs[0].last_emitted
    assert out is not None
    assert out.image.shape == (8, 11, 3)
    np.testing.assert_array_equal(out.image[0:4, 0:5], _bgr(4, 5, 100))
    assert out.image[4:8, 0:5].sum() == 0


def test_mosaic_does_not_fire_until_every_connected_input_has_data() -> None:
    """Connected upstreams gate the dispatch."""
    node = Mosaic()
    node.layout = "12 / 34"
    up_1 = OutputPort("1", {IoDataType.IMAGE})
    up_2 = OutputPort("2", {IoDataType.IMAGE})
    up_3 = OutputPort("3", {IoDataType.IMAGE})
    up_1.connect(node.inputs[0])
    up_2.connect(node.inputs[1])
    up_3.connect(node.inputs[2])

    up_1.send(IoData.from_image(_bgr(2, 2, 1)))
    up_2.send(IoData.from_image(_bgr(2, 2, 2)))
    assert node.outputs[0].last_emitted is None

    up_3.send(IoData.from_image(_bgr(2, 2, 3)))
    assert node.outputs[0].last_emitted is not None


def test_mosaic_invalid_layout_raises_at_process_time() -> None:
    node = Mosaic()
    node.layout = "12 / 21"
    with pytest.raises(ValueError, match="rectangle"):
        _wire(node, {
            "1": IoData.from_image(_bgr(2, 2, 10)),
            "2": IoData.from_image(_bgr(2, 2, 20)),
        })

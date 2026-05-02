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
    layout = MosaicLayout("1,2")
    assert layout.rows == [[0, 1]]


def test_layout_vertical_pair() -> None:
    layout = MosaicLayout("1;2")
    assert layout.rows == [[0], [1]]


def test_layout_2x2_grid() -> None:
    layout = MosaicLayout("1,2;3,4")
    assert layout.rows == [[0, 1], [2, 3]]


def test_layout_uneven_rows_are_allowed() -> None:
    """No grid → rows can have different cell counts.
    Row 2 will be scaled to row 1's width at render time."""
    layout = MosaicLayout("1,2;3")
    assert layout.rows == [[0, 1], [2]]


def test_layout_whitespace_around_tokens_is_ignored() -> None:
    a = MosaicLayout("1, 2 ; 3 ,4")
    b = MosaicLayout("1,2;3,4")
    assert a.rows == b.rows


def test_layout_trailing_semicolon_is_tolerated() -> None:
    assert MosaicLayout("1,2;3;").rows == [[0, 1], [2]]
    assert MosaicLayout("1,2;").rows == [[0, 1]]


def test_layout_blank_rows_are_skipped() -> None:
    """A run of ``;`` collapses to a single row break."""
    assert MosaicLayout("1;;2").rows == [[0], [1]]


def test_layout_multi_digit_indices() -> None:
    """Syntax has no upper bound — only the input pool does.
    Parser accepts large indices; render time skips out-of-range."""
    layout = MosaicLayout("10,11;12")
    assert layout.rows == [[9, 10], [11]]


def test_layout_rejects_empty_cell_token() -> None:
    with pytest.raises(ValueError, match="empty cell"):
        MosaicLayout("1,,2")


def test_layout_rejects_trailing_comma() -> None:
    with pytest.raises(ValueError, match="empty cell"):
        MosaicLayout("1,2,")


def test_layout_rejects_non_integer_token() -> None:
    with pytest.raises(ValueError, match="not an integer"):
        MosaicLayout("1,A")


def test_layout_rejects_zero_or_negative() -> None:
    with pytest.raises(ValueError, match="1-based"):
        MosaicLayout("1,0")
    with pytest.raises(ValueError, match="1-based"):
        MosaicLayout("-1,2")


def test_layout_rejects_empty_descriptor() -> None:
    with pytest.raises(ValueError, match="empty"):
        MosaicLayout("")
    with pytest.raises(ValueError, match="empty"):
        MosaicLayout("   ;  ;")


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


def _wire(node: Mosaic, idx_to_data: dict[int, IoData]) -> None:
    """Connect a fake upstream per used 1-based index, then send all data.

    Mosaic only fires once every connected input has data, so every
    upstream must be connected before any send() runs.
    """
    upstreams: list[tuple[OutputPort, IoData]] = []
    for one_based, data in idx_to_data.items():
        up = OutputPort(str(one_based), {data.type})
        up.connect(node.inputs[one_based - 1])
        upstreams.append((up, data))
    for up, data in upstreams:
        up.send(data)


def test_default_layout_is_horizontal_pair() -> None:
    node = Mosaic()
    _wire(node, {
        1: IoData.from_image(_bgr(4, 6, 10)),
        2: IoData.from_image(_bgr(4, 6, 20)),
    })
    out = node.outputs[0].last_emitted
    assert out is not None
    assert out.image.shape == (4, 12, 3)
    assert out.image[0, 0, 0] == 10
    assert out.image[0, 6, 0] == 20


def test_vertical_stack_same_width() -> None:
    node = Mosaic()
    node.layout = "1;2"
    _wire(node, {
        1: IoData.from_image(_bgr(4, 6, 10)),
        2: IoData.from_image(_bgr(4, 6, 20)),
    })
    out = node.outputs[0].last_emitted
    assert out is not None
    assert out.image.shape == (8, 6, 3)
    assert out.image[0, 0, 0] == 10
    assert out.image[4, 0, 0] == 20


def test_2x2_grid_color_inputs() -> None:
    node = Mosaic()
    node.layout = "1,2;3,4"
    _wire(node, {
        1: IoData.from_image(_bgr(4, 6, 10)),
        2: IoData.from_image(_bgr(4, 6, 20)),
        3: IoData.from_image(_bgr(4, 6, 30)),
        4: IoData.from_image(_bgr(4, 6, 40)),
    })
    out = node.outputs[0].last_emitted
    assert out is not None
    assert out.image.shape == (8, 12, 3)
    assert out.image[0, 0, 0] == 10
    assert out.image[0, 6, 0] == 20
    assert out.image[4, 0, 0] == 30
    assert out.image[4, 6, 0] == 40


def test_row_height_match_preserves_aspect() -> None:
    """Row 1 has image_1 4x4 and image_2 8x8 → both scaled to height 8.
    image_1's width grows proportionally from 4 to 8."""
    node = Mosaic()
    node.layout = "1,2"
    _wire(node, {
        1: IoData.from_image(_bgr(4, 4, 10)),
        2: IoData.from_image(_bgr(8, 8, 20)),
    })
    out = node.outputs[0].last_emitted
    assert out is not None
    # row height = 8, image_1 scales to 8x8, image_2 stays 8x8 → 8x16
    assert out.image.shape == (8, 16, 3)


def test_row_width_match_preserves_aspect() -> None:
    """Row 1 is 16 wide (8+8), row 2 is 8 wide → row 2 scales to 16
    wide, height doubles too. No black bars."""
    node = Mosaic()
    node.layout = "1,2;3"
    _wire(node, {
        1: IoData.from_image(_bgr(8, 8, 10)),
        2: IoData.from_image(_bgr(8, 8, 20)),
        3: IoData.from_image(_bgr(8, 8, 30)),
    })
    out = node.outputs[0].last_emitted
    assert out is not None
    # row 1: 8 high, 16 wide. row 2: image_3 8x8 scaled to 16 wide → 16x16.
    # vstack → 24 high, 16 wide.
    assert out.image.shape == (24, 16, 3)


def test_uneven_row_widths_no_black_bars() -> None:
    """Reproduces the data_display_time_series_merged.flowjs scenario:
    PlotXY (800x800) + PlotSeries (1600x800) in row 1 → naturally 2400
    wide; PolarHeatmap (2400x2400) in row 2 → 2400 wide. Both rows
    already match the widest row width, so no scaling is needed and
    the canvas is exactly 2400 pixels wide."""
    node = Mosaic()
    node.layout = "1,2;3"
    _wire(node, {
        1: IoData.from_image(_bgr(800, 800, 10)),
        2: IoData.from_image(_bgr(800, 1600, 20)),
        3: IoData.from_image(_bgr(2400, 2400, 30)),
    })
    out = node.outputs[0].last_emitted
    assert out is not None
    assert out.image.shape[1] == 2400
    # row 1 = 800 high, row 2 = 2400 high → total 3200
    assert out.image.shape == (3200, 2400, 3)


def test_all_greyscale_inputs_emit_greyscale() -> None:
    node = Mosaic()
    node.layout = "1,2;3,4"
    _wire(node, {
        1: IoData.from_greyscale(_grey(3, 3, 10)),
        2: IoData.from_greyscale(_grey(3, 3, 20)),
        3: IoData.from_greyscale(_grey(3, 3, 30)),
        4: IoData.from_greyscale(_grey(3, 3, 40)),
    })
    out = node.outputs[0].last_emitted
    assert out is not None
    assert out.type == IoDataType.IMAGE_GREY
    assert out.image.shape == (6, 6)


def test_mixed_types_promote_to_color() -> None:
    node = Mosaic()
    node.layout = "1,2"
    _wire(node, {
        1: IoData.from_greyscale(_grey(2, 2, 77)),
        2: IoData.from_image(_bgr(2, 2, 200)),
    })
    out = node.outputs[0].last_emitted
    assert out is not None
    assert out.type == IoDataType.IMAGE
    np.testing.assert_array_equal(out.image[0:2, 0:2], _bgr(2, 2, 77))
    np.testing.assert_array_equal(out.image[0:2, 2:4], _bgr(2, 2, 200))


def test_unconnected_cells_are_dropped_from_their_row() -> None:
    """``"1,2;3,4"`` but only image_1 and image_4 wired — image_2 is
    silently dropped from row 1, image_3 from row 2. Row 1 then holds
    just image_1, row 2 just image_4. No black padding cells."""
    node = Mosaic()
    node.layout = "1,2;3,4"
    _wire(node, {
        1: IoData.from_image(_bgr(4, 5, 111)),
        4: IoData.from_image(_bgr(4, 5, 222)),
    })
    out = node.outputs[0].last_emitted
    assert out is not None
    # row 1: image_1 4x5; row 2: image_4 4x5; both already 5 wide.
    assert out.image.shape == (8, 5, 3)
    np.testing.assert_array_equal(out.image[0:4, 0:5], _bgr(4, 5, 111))
    np.testing.assert_array_equal(out.image[4:8, 0:5], _bgr(4, 5, 222))


def test_row_with_only_unconnected_cells_is_dropped() -> None:
    """``"1;2"`` but image_2 unwired → output is just image_1."""
    node = Mosaic()
    node.layout = "1;2"
    _wire(node, {1: IoData.from_image(_bgr(4, 6, 111))})
    out = node.outputs[0].last_emitted
    assert out is not None
    assert out.image.shape == (4, 6, 3)


def test_does_not_fire_until_every_connected_input_has_data() -> None:
    """Connected upstreams gate the dispatch."""
    node = Mosaic()
    node.layout = "1,2;3,4"
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


def test_invalid_layout_raises_at_process_time() -> None:
    node = Mosaic()
    node.layout = "1,,2"
    with pytest.raises(ValueError, match="empty cell"):
        _wire(node, {1: IoData.from_image(_bgr(2, 2, 10))})

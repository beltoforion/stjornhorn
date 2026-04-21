"""Unit tests for the Merge (2x2 composite) node."""
from __future__ import annotations

import numpy as np

from core.io_data import IoData, IoDataType
from core.port import OutputPort
from nodes.filters.merge import Merge


def _bgr(h: int, w: int, value: int) -> np.ndarray:
    return np.full((h, w, 3), value, dtype=np.uint8)


def _grey(h: int, w: int, value: int) -> np.ndarray:
    return np.full((h, w), value, dtype=np.uint8)


def _wire(node: Merge, quadrants: dict[str, IoData]) -> None:
    """Connect a fake upstream per quadrant, then send all the data.

    Merge only fires once every *connected* input has data, so every
    upstream must be connected before any send() runs — otherwise the
    node fires after the first frame with only one input ready.
    """
    upstreams: list[tuple[OutputPort, IoData]] = []
    for name, data in quadrants.items():
        idx = node._QUADRANTS.index(name)
        up = OutputPort(name, {data.type})
        up.connect(node.inputs[idx])
        upstreams.append((up, data))
    for up, data in upstreams:
        up.send(data)


def test_merge_all_four_color_inputs_builds_2x2_grid() -> None:
    node = Merge()
    _wire(node, {
        "top_left":     IoData.from_image(_bgr(4, 6, 10)),
        "top_right":    IoData.from_image(_bgr(4, 6, 20)),
        "bottom_left":  IoData.from_image(_bgr(4, 6, 30)),
        "bottom_right": IoData.from_image(_bgr(4, 6, 40)),
    })

    out = node.outputs[0].last_emitted
    assert out is not None
    assert out.type == IoDataType.IMAGE
    assert out.image.shape == (8, 12, 3)
    assert out.image[0, 0, 0] == 10
    assert out.image[0, 6, 0] == 20
    assert out.image[4, 0, 0] == 30
    assert out.image[4, 6, 0] == 40


def test_merge_all_greyscale_inputs_emits_greyscale() -> None:
    node = Merge()
    _wire(node, {
        "top_left":     IoData.from_greyscale(_grey(3, 5, 10)),
        "top_right":    IoData.from_greyscale(_grey(3, 5, 20)),
        "bottom_left":  IoData.from_greyscale(_grey(3, 5, 30)),
        "bottom_right": IoData.from_greyscale(_grey(3, 5, 40)),
    })

    out = node.outputs[0].last_emitted
    assert out is not None
    assert out.type == IoDataType.IMAGE_GREY
    assert out.image.shape == (6, 10)
    assert out.image[0, 0] == 10
    assert out.image[0, 5] == 20
    assert out.image[3, 0] == 30
    assert out.image[3, 5] == 40


def test_merge_mixed_types_promotes_to_color() -> None:
    node = Merge()
    _wire(node, {
        "top_left":  IoData.from_greyscale(_grey(2, 2, 77)),
        "top_right": IoData.from_image(_bgr(2, 2, 200)),
    })

    out = node.outputs[0].last_emitted
    assert out is not None
    assert out.type == IoDataType.IMAGE
    # Grey quadrant is promoted to BGR, so every channel should equal 77.
    np.testing.assert_array_equal(out.image[0:2, 0:2], _bgr(2, 2, 77))
    np.testing.assert_array_equal(out.image[0:2, 2:4], _bgr(2, 2, 200))


def test_merge_partial_inputs_pads_missing_quadrants_with_black() -> None:
    node = Merge()
    # Only TL and BR connected — canvas size comes from those two, TR and
    # BL cells stay zero.
    _wire(node, {
        "top_left":     IoData.from_image(_bgr(4, 5, 111)),
        "bottom_right": IoData.from_image(_bgr(6, 7, 222)),
    })

    out = node.outputs[0].last_emitted
    assert out is not None
    assert out.image.shape == (10, 12, 3)
    np.testing.assert_array_equal(out.image[0:4, 0:5], _bgr(4, 5, 111))
    np.testing.assert_array_equal(out.image[4:10, 5:12], _bgr(6, 7, 222))
    # Missing TR cell (rows 0:4, cols 5:12) is black.
    assert out.image[0:4, 5:12].sum() == 0
    # Missing BL cell (rows 4:10, cols 0:5) is black.
    assert out.image[4:10, 0:5].sum() == 0


def test_merge_row_and_column_heights_take_per_axis_max() -> None:
    node = Merge()
    _wire(node, {
        "top_left":  IoData.from_image(_bgr(4, 5, 10)),  # tall + narrow
        "top_right": IoData.from_image(_bgr(2, 7, 20)),  # short + wide
    })

    out = node.outputs[0].last_emitted
    assert out is not None
    # top_h = max(4, 2) = 4; bottom row is empty so bottom_h = 0;
    # left_w = 5; right_w = 7 → canvas = (4, 12).
    assert out.image.shape == (4, 12, 3)
    # TR is 2 rows tall but its cell is 4 rows — rows 2:4, cols 5:12 are pad.
    assert out.image[2:4, 5:12].sum() == 0


def test_merge_does_not_fire_until_every_connected_input_has_data() -> None:
    node = Merge()
    # Connect upstreams but only push data into two of them.
    up0 = OutputPort("a", {IoDataType.IMAGE})
    up1 = OutputPort("b", {IoDataType.IMAGE})
    up2 = OutputPort("c", {IoDataType.IMAGE})
    up0.connect(node.inputs[0])
    up1.connect(node.inputs[1])
    up2.connect(node.inputs[2])
    up0.send(IoData.from_image(_bgr(2, 2, 1)))
    up1.send(IoData.from_image(_bgr(2, 2, 2)))

    assert node.outputs[0].last_emitted is None

    up2.send(IoData.from_image(_bgr(2, 2, 3)))
    assert node.outputs[0].last_emitted is not None


def test_merge_forwards_finish_once_every_connected_input_finishes() -> None:
    from core.port import InputPort

    node = Merge()
    up0 = OutputPort("a", {IoDataType.IMAGE})
    up1 = OutputPort("b", {IoDataType.IMAGE})
    up0.connect(node.inputs[0])
    up1.connect(node.inputs[1])

    sink = InputPort("sink", {IoDataType.IMAGE})
    node.outputs[0].connect(sink)

    # Only one upstream finishing is not enough — the other is still live.
    up0.finish()
    assert not sink.finished
    assert not node.outputs[0].finished

    up1.finish()
    assert sink.finished
    assert node.outputs[0].finished

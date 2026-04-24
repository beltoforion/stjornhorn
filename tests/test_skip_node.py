"""Unit tests for the node skip (pass-through) feature."""
from __future__ import annotations

import numpy as np
import pytest

from core.io_data import IoData, IoDataType
from core.port import InputPort, OutputPort
from nodes.filters.dither import Dither
from nodes.filters.grayscale import Grayscale
from nodes.filters.median import Median
from nodes.filters.ncc import Ncc
from nodes.filters.rgb_join import RgbJoin
from nodes.filters.shift import Shift
from nodes.sinks.file_sink import FileSink
from nodes.sources.image_source import ImageSource


def test_median_is_skippable() -> None:
    """Median has a single in/out port pair with identical accepted/emit types."""
    assert Median().is_skippable is True


def test_shift_is_skippable() -> None:
    assert Shift().is_skippable is True


def test_dither_is_not_skippable() -> None:
    """Dither accepts colour or greyscale but only emits greyscale — bypassing
    could forward a colour image onto a greyscale-only downstream port."""
    assert Dither().is_skippable is False


def test_grayscale_is_not_skippable() -> None:
    assert Grayscale().is_skippable is False


def test_ncc_is_not_skippable() -> None:
    """Two inputs, one output — no one-to-one mapping."""
    assert Ncc().is_skippable is False


def test_rgb_join_is_not_skippable() -> None:
    """Three inputs, one output — cannot forward pairwise."""
    assert RgbJoin().is_skippable is False


def test_source_and_sink_are_not_skippable() -> None:
    assert ImageSource().is_skippable is False
    assert FileSink().is_skippable is False


def test_setting_skipped_on_non_skippable_raises() -> None:
    node = Dither()
    with pytest.raises(ValueError):
        node.skipped = True


def test_skipped_node_forwards_input_to_output_unchanged() -> None:
    """A skipped node's outputs emit the input payload by reference."""
    node = Median()
    node.size = 7  # would otherwise blur the image
    node.skipped = True

    out_capture = InputPort("cap", {IoDataType.IMAGE})
    node.outputs[0].connect(out_capture)

    image = np.arange(16, dtype=np.uint8).reshape(4, 4)
    image = np.stack([image, image, image], axis=-1)
    node.inputs[0].receive(IoData.from_image(image))

    assert out_capture.has_data
    np.testing.assert_array_equal(out_capture.data.image, image)


def test_unskipping_restores_normal_processing() -> None:
    node = Median()
    node.size = 3
    node.skipped = True
    node.skipped = False

    out_capture = InputPort("cap", {IoDataType.IMAGE})
    node.outputs[0].connect(out_capture)

    image = np.zeros((8, 8, 3), dtype=np.uint8)
    image[0, 0] = (255, 255, 255)
    node.inputs[0].receive(IoData.from_image(image))

    # Median with a 3×3 kernel erases a single-pixel spike.
    assert out_capture.has_data
    assert out_capture.data.image[0, 0].tolist() == [0, 0, 0]

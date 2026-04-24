"""Unit tests for the most basic end-to-end flow: source -> sink."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from core.io_data import IoDataType
from core.port import InputPort
from nodes.sinks.file_sink import FileSink
from nodes.sources.image_source import ImageSource


def test_image_source_to_file_sink_saves_image(tmp_path: Path) -> None:
    """An ImageSource wired to a FileSink should, after source.start(),
    write the frame the source read to the sink's output path."""
    in_path = tmp_path / "in.png"
    out_path = tmp_path / "out.png"

    # Write a small, distinctive synthetic image so we can assert on the
    # exact bytes that come out of the sink.
    expected = np.full((8, 8, 3), fill_value=128, dtype=np.uint8)
    assert cv2.imwrite(str(in_path), expected), "failed to write input fixture"

    source = ImageSource()
    source.file_path = in_path

    sink = FileSink()
    sink.output_path = str(out_path)

    # Wire source -> sink and drive the flow by starting the source directly.
    source.outputs[0].connect(sink.inputs[0])
    source.start()

    assert out_path.exists(), "sink did not write an output file"
    loaded = cv2.imread(str(out_path))
    assert loaded is not None, "sink wrote a file but it is not a readable image"
    np.testing.assert_array_equal(loaded, expected)


def test_image_source_preserves_rgba_alpha_channel(tmp_path: Path) -> None:
    """PNG / WebP files with an alpha channel must reach downstream nodes
    with 4 channels intact — IMREAD_UNCHANGED, not IMREAD_COLOR."""
    in_path = tmp_path / "rgba.png"
    rgba = np.empty((4, 4, 4), dtype=np.uint8)
    rgba[..., :3] = 50
    rgba[..., 3] = np.array(
        [[0, 64, 128, 255]] * 4, dtype=np.uint8
    )
    assert cv2.imwrite(str(in_path), rgba), "failed to write RGBA fixture"

    source = ImageSource()
    source.file_path = in_path

    capture = InputPort("cap", {IoDataType.IMAGE})
    source.outputs[0].connect(capture)
    source.start()

    assert capture.has_data
    image = capture.data.image
    assert image.shape == (4, 4, 4), f"expected BGRA, got shape {image.shape}"
    np.testing.assert_array_equal(image[..., 3], rgba[..., 3])


def test_image_source_promotes_greyscale_png_to_bgr(tmp_path: Path) -> None:
    """A single-channel PNG must be promoted to 3-channel BGR so the
    IoDataType.IMAGE contract (≥ 3 channels) holds."""
    in_path = tmp_path / "grey.png"
    grey = np.full((4, 4), 77, dtype=np.uint8)
    assert cv2.imwrite(str(in_path), grey), "failed to write greyscale fixture"

    source = ImageSource()
    source.file_path = in_path

    capture = InputPort("cap", {IoDataType.IMAGE})
    source.outputs[0].connect(capture)
    source.start()

    assert capture.has_data
    image = capture.data.image
    assert image.ndim == 3 and image.shape[2] == 3
    np.testing.assert_array_equal(image[..., 0], 77)

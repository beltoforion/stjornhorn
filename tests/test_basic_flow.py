"""Unit tests for the most basic end-to-end flow: source -> sink."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from nodes.sinks.file_sink import FileSink
from nodes.sources.file_source import FileSource


def test_file_source_to_file_sink_saves_image(tmp_path: Path) -> None:
    """A FileSource wired to a FileSink should, after source.start(),
    write the frame the source read to the sink's output path."""
    in_path = tmp_path / "in.png"
    out_path = tmp_path / "out.png"

    # Write a small, distinctive synthetic image so we can assert on the
    # exact bytes that come out of the sink.
    expected = np.full((8, 8, 3), fill_value=128, dtype=np.uint8)
    assert cv2.imwrite(str(in_path), expected), "failed to write input fixture"

    source = FileSource()
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

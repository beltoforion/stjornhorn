"""Unit tests for the Display node.

Display is Qt-free — the inline preview widget lives on the UI side.
These tests exercise the node's pass-through semantics, its
``latest_frame`` snapshot and the optional frame callback.
"""
from __future__ import annotations

import numpy as np

from core.io_data import IoData, IoDataType
from core.port import InputPort, OutputPort
from nodes.filters.display import Display


def _wire(node: Display) -> tuple[OutputPort, list[IoData]]:
    up = OutputPort("frames", {IoDataType.IMAGE})
    up.connect(node.inputs[0])

    captured: list[IoData] = []
    sink = InputPort("sink", {IoDataType.IMAGE})
    sink.set_on_state_changed(
        lambda: captured.append(sink.data) if sink.has_data else None
    )
    node.outputs[0].connect(sink)
    return up, captured


def _bgr(value: int = 100, h: int = 16, w: int = 24) -> np.ndarray:
    return np.full((h, w, 3), value, dtype=np.uint8)


def test_display_passes_input_through_unchanged() -> None:
    node = Display()
    up, captured = _wire(node)

    node.before_run()
    for v in (20, 90, 180):
        up.send(IoData.from_image(_bgr(v)))

    assert len(captured) == 3
    for original_value, emitted in zip((20, 90, 180), captured):
        assert emitted.type == IoDataType.IMAGE
        assert int(emitted.image[0, 0, 0]) == original_value


def test_display_tracks_latest_frame() -> None:
    node = Display()
    up, _ = _wire(node)

    node.before_run()
    assert node.latest_frame is None

    up.send(IoData.from_image(_bgr(40)))
    assert node.latest_frame is not None
    assert int(node.latest_frame[0, 0, 0]) == 40

    up.send(IoData.from_image(_bgr(200)))
    assert int(node.latest_frame[0, 0, 0]) == 200


def test_display_invokes_frame_callback_per_frame() -> None:
    node = Display()
    up, _ = _wire(node)

    received: list[np.ndarray] = []
    node.set_frame_callback(received.append)

    node.before_run()
    for v in (10, 50, 130):
        up.send(IoData.from_image(_bgr(v)))

    assert len(received) == 3
    assert [int(f[0, 0, 0]) for f in received] == [10, 50, 130]


def test_display_can_clear_frame_callback() -> None:
    node = Display()
    up, _ = _wire(node)

    received: list[np.ndarray] = []
    node.set_frame_callback(received.append)
    node.set_frame_callback(None)

    node.before_run()
    up.send(IoData.from_image(_bgr()))

    assert received == []


def test_display_passes_through_greyscale() -> None:
    node = Display()
    up = OutputPort("frames", {IoDataType.IMAGE_GREY})
    up.connect(node.inputs[0])
    captured: list[IoData] = []
    sink = InputPort("sink", {IoDataType.IMAGE_GREY})
    sink.set_on_state_changed(
        lambda: captured.append(sink.data) if sink.has_data else None
    )
    node.outputs[0].connect(sink)

    node.before_run()
    up.send(IoData.from_greyscale(np.full((8, 12), 50, dtype=np.uint8)))

    assert captured[0].type == IoDataType.IMAGE_GREY
    assert captured[0].image.shape == (8, 12)
    assert node.latest_frame is not None
    assert node.latest_frame.shape == (8, 12)


def test_display_resets_latest_frame_on_new_run() -> None:
    node = Display()
    up, _ = _wire(node)

    node.before_run()
    up.send(IoData.from_image(_bgr()))
    assert node.latest_frame is not None

    node.before_run()  # new run
    assert node.latest_frame is None


def test_display_forwards_finish() -> None:
    node = Display()
    up, _ = _wire(node)
    sink = node.outputs[0].connections[0]

    node.before_run()
    up.send(IoData.from_image(_bgr()))
    up.finish()

    assert sink.finished
    assert node.outputs[0].finished


def test_display_has_no_params() -> None:
    # FPS overlay is unconditional — no user-facing knobs to expose.
    assert Display().params == []


def test_display_fps_overlay_does_not_leak_to_output() -> None:
    # The overlay is for the preview only; the output port must still
    # forward the original IoData byte-for-byte so downstream sinks
    # (e.g. VideoSink) record clean frames.
    node = Display()
    up, captured = _wire(node)

    received: list[np.ndarray] = []
    node.set_frame_callback(received.append)

    node.before_run()
    # Big enough that the FPS rect (≈ 90 × 25 px in the top-left) leaves
    # plenty of unmodified canvas for the leak check.
    big = lambda v: np.full((128, 256, 3), v, dtype=np.uint8)
    for v in (60, 120, 200):
        up.send(IoData.from_image(big(v)))

    # Output is unmodified everywhere.
    for c, v in zip(captured, (60, 120, 200)):
        np.testing.assert_array_equal(c.image, big(v))
    # Preview callback gets the annotated frame, but the bottom-right
    # corner (well outside the overlay box) is still untouched.
    for f, v in zip(received, (60, 120, 200)):
        assert int(f[-1, -1, 0]) == v


def test_display_fps_overlay_writes_visible_pixels_on_preview() -> None:
    # Sanity-check that the overlay actually paints something. The first
    # frame has no measurable dt → overlay can't render yet, but every
    # frame after that should have a black rectangle in the top-left.
    node = Display()
    received: list[np.ndarray] = []
    node.set_frame_callback(received.append)
    up, _ = _wire(node)

    node.before_run()
    for _ in range(3):
        up.send(IoData.from_image(_bgr(100, h=64, w=128)))

    np.testing.assert_array_equal(received[0], _bgr(100, h=64, w=128))
    # On the second frame the overlay rect lives in the top-left.
    # Pixel (5, 50) sits in the rect's clear space above the text glyphs
    # so it should be solid black, distinct from the input fill of 100.
    assert int(received[1][5, 50, 0]) == 0

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

    received: list[IoData] = []
    node.set_frame_callback(received.append)

    node.before_run()
    for v in (10, 50, 130):
        up.send(IoData.from_image(_bgr(v)))

    assert len(received) == 3
    assert [int(d.payload[0, 0, 0]) for d in received] == [10, 50, 130]
    assert all(d.type is IoDataType.IMAGE for d in received)


def test_display_can_clear_frame_callback() -> None:
    node = Display()
    up, _ = _wire(node)

    received: list[IoData] = []
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
    # An inline preview makes window_title meaningless — Display
    # deliberately exposes no params so it stays purely a live view.
    assert Display().params == []


# ── SCALAR / MATRIX support ───────────────────────────────────────────────────

def test_display_passes_through_scalar() -> None:
    node = Display()
    up = OutputPort("vals", {IoDataType.SCALAR})
    up.connect(node.inputs[0])
    captured: list[IoData] = []
    sink = InputPort("sink", {IoDataType.SCALAR})
    sink.set_on_state_changed(
        lambda: captured.append(sink.data) if sink.has_data else None
    )
    node.outputs[0].connect(sink)

    node.before_run()
    for v in (3, 7, 11):
        up.send(IoData.from_scalar(v))

    assert [d.type for d in captured] == [IoDataType.SCALAR] * 3
    assert [int(d.payload.item()) for d in captured] == [3, 7, 11]
    # latest_frame stores the payload (a 0-d array for scalars).
    assert node.latest_frame is not None
    assert node.latest_frame.ndim == 0
    assert int(node.latest_frame.item()) == 11


def test_display_invokes_callback_with_scalar_iodata() -> None:
    node = Display()
    up = OutputPort("vals", {IoDataType.SCALAR})
    up.connect(node.inputs[0])

    received: list[IoData] = []
    node.set_frame_callback(received.append)

    node.before_run()
    up.send(IoData.from_scalar(42))

    assert len(received) == 1
    assert received[0].type is IoDataType.SCALAR
    assert int(received[0].payload.item()) == 42


def test_display_passes_through_matrix() -> None:
    node = Display()
    up = OutputPort("mat", {IoDataType.MATRIX})
    up.connect(node.inputs[0])
    captured: list[IoData] = []
    sink = InputPort("sink", {IoDataType.MATRIX})
    sink.set_on_state_changed(
        lambda: captured.append(sink.data) if sink.has_data else None
    )
    node.outputs[0].connect(sink)

    m = np.array([[1.0, 2.0], [3.0, 4.0]])
    node.before_run()
    up.send(IoData.from_matrix(m))

    assert captured[0].type is IoDataType.MATRIX
    assert captured[0].payload.shape == (2, 2)
    assert node.latest_frame is not None
    assert node.latest_frame.shape == (2, 2)

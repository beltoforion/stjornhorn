"""Unit tests for the Display node.

The sandbox has no HighGUI backend, so cv2.imshow / cv2.waitKey /
cv2.namedWindow / cv2.destroyWindow are monkeypatched. The tests
assert on the calls rather than on visible windows.
"""
from __future__ import annotations

from typing import Any

import cv2
import numpy as np
import pytest

from core.io_data import IoData, IoDataType
from core.port import InputPort, OutputPort
from nodes.filters.display import Display


class _HighGuiSpy:
    """Captures imshow / window-lifecycle calls and reports them back."""

    def __init__(self) -> None:
        self.imshow_calls: list[tuple[str, tuple[int, ...]]] = []
        self.opened: list[str] = []
        self.destroyed: list[str] = []
        self.wait_keys: int = 0

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            cv2, "imshow",
            lambda title, img: self.imshow_calls.append((title, img.shape)),
        )
        def _wait_key(_timeout: int = 0) -> int:
            self.wait_keys += 1
            return -1
        monkeypatch.setattr(cv2, "waitKey", _wait_key)
        monkeypatch.setattr(cv2, "namedWindow", lambda title, *_: self.opened.append(title))
        monkeypatch.setattr(cv2, "destroyWindow", lambda title: self.destroyed.append(title))


def _wire_colour(node: Display) -> tuple[OutputPort, list[IoData]]:
    up = OutputPort("frames", {IoDataType.IMAGE})
    up.connect(node.inputs[0])

    captured: list[IoData] = []
    sink = InputPort("sink", {IoDataType.IMAGE})
    sink.set_on_state_changed(
        lambda: captured.append(sink.data) if sink.has_data else None
    )
    node.outputs[0].connect(sink)
    return up, captured


def _bgr(value: int = 100) -> np.ndarray:
    return np.full((16, 24, 3), value, dtype=np.uint8)


def test_display_shows_and_passes_each_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    spy = _HighGuiSpy()
    spy.install(monkeypatch)

    node = Display()
    up, captured = _wire_colour(node)

    node.before_run()
    for v in (20, 90, 180):
        up.send(IoData.from_image(_bgr(v)))
    node.after_run(True)

    # imshow was called once per frame, always on the same window.
    assert len(spy.imshow_calls) == 3
    assert {title for title, _ in spy.imshow_calls} == {"Display"}
    # waitKey(1) pumps the event loop after each imshow.
    assert spy.wait_keys == 3
    # Window opened lazily on first frame, exactly once.
    assert spy.opened == ["Display"]
    # Pass-through: every input is emitted unchanged.
    assert len(captured) == 3
    for original_value, emitted in zip((20, 90, 180), captured):
        assert emitted.type == IoDataType.IMAGE
        assert int(emitted.image[0, 0, 0]) == original_value


def test_display_passes_through_greyscale(monkeypatch: pytest.MonkeyPatch) -> None:
    spy = _HighGuiSpy()
    spy.install(monkeypatch)

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
    node.after_run(True)

    # imshow received the 2-D array as-is (HighGUI handles greyscale directly).
    assert spy.imshow_calls == [("Display", (8, 12))]
    assert captured[0].type == IoDataType.IMAGE_GREY


def test_display_destroys_window_before_next_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spy = _HighGuiSpy()
    spy.install(monkeypatch)

    node = Display()
    up, _ = _wire_colour(node)

    node.before_run()
    up.send(IoData.from_image(_bgr()))
    node.after_run(True)  # success: window kept open

    assert spy.destroyed == []

    node.before_run()  # starting a new run should tear the old window down
    assert spy.destroyed == ["Display"]
    up.send(IoData.from_image(_bgr()))
    node.after_run(True)

    # Two distinct runs → two lazy window opens.
    assert spy.opened == ["Display", "Display"]


def test_display_destroys_window_on_failed_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spy = _HighGuiSpy()
    spy.install(monkeypatch)

    node = Display()
    up, _ = _wire_colour(node)

    node.before_run()
    up.send(IoData.from_image(_bgr()))
    node.after_run(False)

    assert spy.destroyed == ["Display"]


def test_display_rename_closes_previous_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spy = _HighGuiSpy()
    spy.install(monkeypatch)

    node = Display()
    up, _ = _wire_colour(node)

    node.before_run()
    up.send(IoData.from_image(_bgr()))
    node.window_title = "After"
    up.send(IoData.from_image(_bgr()))
    node.after_run(True)

    # Old "Display" window destroyed; new "After" window opened.
    assert spy.destroyed == ["Display"]
    assert spy.opened == ["Display", "After"]


def test_display_rejects_empty_window_title() -> None:
    node = Display()
    with pytest.raises(ValueError):
        node.window_title = "   "


def test_display_forwards_finish(monkeypatch: pytest.MonkeyPatch) -> None:
    spy = _HighGuiSpy()
    spy.install(monkeypatch)

    node = Display()
    up, _ = _wire_colour(node)
    sink = node.outputs[0].connections[0]

    node.before_run()
    up.send(IoData.from_image(_bgr()))
    up.finish()

    assert sink.finished
    assert node.outputs[0].finished

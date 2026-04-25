"""Unit tests for the ValueSink sink node."""
from __future__ import annotations

import numpy as np

from core.io_data import IoData, IoDataType
from core.port import OutputPort
from nodes.sinks.value_sink import ValueSink


def test_consumes_scalar_payloads() -> None:
    sink = ValueSink()
    up = OutputPort("vals", {IoDataType.SCALAR})
    up.connect(sink.inputs[0])

    sink.before_run()
    for v in (1, 2, 3):
        up.send(IoData.from_scalar(v))

    assert sink.latest_value is not None
    assert sink.latest_value.ndim == 0
    assert int(sink.latest_value.item()) == 3


def test_consumes_matrix_payloads() -> None:
    sink = ValueSink()
    up = OutputPort("mat", {IoDataType.MATRIX})
    up.connect(sink.inputs[0])

    m = np.array([[1.0, 2.0], [3.0, 4.0]])
    sink.before_run()
    up.send(IoData.from_matrix(m))

    assert sink.latest_value is not None
    assert sink.latest_value.shape == (2, 2)
    assert sink.latest_value[1, 1] == 4.0


def test_rejects_image_payloads_at_connect_time() -> None:
    """ValueSink declares only SCALAR/MATRIX, so an IMAGE upstream
    can't connect — type mismatch surfaces at link time, not at the
    first frame."""
    sink = ValueSink()
    up = OutputPort("img", {IoDataType.IMAGE})
    assert up.can_connect(sink.inputs[0]) is False


def test_latest_value_resets_on_new_run() -> None:
    sink = ValueSink()
    up = OutputPort("vals", {IoDataType.SCALAR})
    up.connect(sink.inputs[0])

    sink.before_run()
    up.send(IoData.from_scalar(7))
    assert sink.latest_value is not None

    sink.before_run()  # new run
    assert sink.latest_value is None


def test_value_sink_has_no_outputs() -> None:
    sink = ValueSink()
    assert sink.outputs == []

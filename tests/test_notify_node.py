"""Tests for the ``Notify`` node.

Covers:
  - The three severities (INFO / WARNING via the hub, ERROR via raise).
  - The image input is forwarded unchanged.
  - The ``message`` port can be driven by an upstream STRING source.
  - Severity setter rejects bogus values.
"""

from __future__ import annotations

import numpy as np
import pytest

from core import notifications
from core.io_data import IoData, IoDataType
from core.port import OutputPort
from nodes.filters.notify import Notify, NotifySeverity


@pytest.fixture(autouse=True)
def _isolated_subscribers():
    saved = list(notifications._subscribers)
    notifications._subscribers.clear()
    yield
    notifications._subscribers.clear()
    notifications._subscribers.extend(saved)


def _frame() -> IoData:
    return IoData.from_image(np.zeros((4, 4, 3), dtype=np.uint8))


def test_default_severity_is_info():
    n = Notify()
    assert n.severity is NotifySeverity.INFO


def test_info_severity_emits_via_hub_and_forwards_input():
    seen: list[tuple[notifications.Severity, str]] = []
    notifications.subscribe(lambda sev, msg: seen.append((sev, msg)))

    n = Notify()
    n.message = "fyi"
    forwarded: list[IoData] = []
    n.outputs[0].connect(_capture_into(forwarded))

    n.inputs[0].receive(_frame())

    assert seen == [(notifications.Severity.INFO, "fyi")]
    assert len(forwarded) == 1


def test_warning_severity_emits_warning():
    seen: list[tuple[notifications.Severity, str]] = []
    notifications.subscribe(lambda sev, msg: seen.append((sev, msg)))

    n = Notify()
    n.severity = NotifySeverity.WARNING
    n.message = "heads up"
    n.inputs[0].receive(_frame())

    assert seen == [(notifications.Severity.WARNING, "heads up")]


def test_error_severity_raises_with_message():
    seen: list[tuple[notifications.Severity, str]] = []
    notifications.subscribe(lambda sev, msg: seen.append((sev, msg)))

    n = Notify()
    n.severity = NotifySeverity.ERROR
    n.message = "kaboom"

    with pytest.raises(RuntimeError, match="kaboom"):
        n.inputs[0].receive(_frame())

    # Errors abort via the exception path; the hub is not used.
    assert seen == []


def test_message_can_be_driven_by_upstream_string_source():
    """The ``message`` input is a port — wiring a STRING producer
    overrides the inline default per frame."""
    seen: list[str] = []
    notifications.subscribe(lambda sev, msg: seen.append(msg))

    n = Notify()
    n.message = "default"  # would be used if the port had no upstream
    n.severity = NotifySeverity.INFO

    upstream = OutputPort("text", {IoDataType.STRING})
    upstream.connect(n.inputs[1])  # inputs[1] is the "message" port

    upstream.send(IoData(IoDataType.STRING, payload="from upstream"))
    n.inputs[0].receive(_frame())

    assert seen == ["from upstream"]


def test_severity_setter_rejects_invalid_value():
    n = Notify()
    with pytest.raises(ValueError):
        n.severity = 99


# ── helpers ────────────────────────────────────────────────────────────────────

def _capture_into(bucket: list[IoData]):
    """Build a sink-style InputPort that appends every received IoData."""
    from core.io_data import IMAGE_TYPES
    from core.port import InputPort

    port = InputPort("sink", set(IMAGE_TYPES))
    port.add_listener(lambda: bucket.append(port.data))
    return port

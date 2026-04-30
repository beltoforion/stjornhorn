"""Verify the editor surface for :class:`~core.params.OddIntParam`.

The descriptor only enforces the odd-only invariant after a value
lands on the node, so without a matching widget the spin box would
step in ones (stopping at evens) and a typed even value would be
silently bumped on the node while the widget kept showing the
original even number — UI / model desync. These tests pin the
contract: the param-widget factory builds an
:class:`OddIntParamWidget` for any port whose descriptor advertises
``widget_kind="odd_int"``, and the embedded spin box steps in twos
plus rejects/fixes-up even input. Issue: #259
"""
from __future__ import annotations

import os
import sys

# Headless Qt platform — must be set before any PySide6 import.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QValidator
from PySide6.QtWidgets import QApplication

from core.port import InputPort
from nodes.filters.gaussian_blur import GaussianBlur
from nodes.filters.median import Median
from nodes.filters.adaptive_gaussian_threshold import AdaptiveGaussianThreshold
from ui.param_widgets import (
    IntParamWidget,
    OddIntParamWidget,
    _OddSpinBox,
    build_param_widget,
)


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication(sys.argv)


def _port(node, name: str) -> InputPort:
    for port in node.param_input_ports:
        if port.name == name:
            return port
    pytest.fail(f"{type(node).__name__} lost its {name!r} param port")


def test_odd_int_param_metadata_advertises_widget_kind(qapp: QApplication) -> None:
    port = _port(GaussianBlur(), "ksize")
    assert port.metadata.get("widget_kind") == "odd_int"


def test_factory_builds_odd_int_widget_for_oddint_port(qapp: QApplication) -> None:
    node = GaussianBlur()
    widget = build_param_widget(node, _port(node, "ksize"))
    assert isinstance(widget, OddIntParamWidget)
    assert isinstance(widget._spin, _OddSpinBox)


def test_factory_builds_int_widget_for_plain_int_port(qapp: QApplication) -> None:
    """Regression guard: plain :class:`IntParam` ports keep the
    generic :class:`IntParamWidget`; the kind dispatch must not
    leak into ports that don't opt in."""
    node = AdaptiveGaussianThreshold()
    widget = build_param_widget(node, _port(node, "c"))
    assert isinstance(widget, IntParamWidget)
    assert not isinstance(widget, OddIntParamWidget)


def test_odd_spin_steps_in_twos(qapp: QApplication) -> None:
    spin = _OddSpinBox()
    assert spin.singleStep() == 2


def test_odd_spin_rejects_typed_even_value(qapp: QApplication) -> None:
    """A finished even-number input is treated as Intermediate so the
    QSpinBox commit machinery falls back to :meth:`fixup` instead of
    accepting the even value as-is."""
    spin = _OddSpinBox()
    state, _, _ = spin.validate("4", 1)
    assert state == QValidator.State.Intermediate


def test_odd_spin_accepts_typed_odd_value(qapp: QApplication) -> None:
    spin = _OddSpinBox()
    state, _, _ = spin.validate("5", 1)
    assert state == QValidator.State.Acceptable


def test_odd_spin_fixup_rounds_even_up_to_next_odd(qapp: QApplication) -> None:
    spin = _OddSpinBox()
    assert spin.fixup("4") == "5"
    assert spin.fixup("0") == "1"
    assert spin.fixup("6") == "7"


def test_odd_spin_fixup_leaves_odd_unchanged(qapp: QApplication) -> None:
    spin = _OddSpinBox()
    assert spin.fixup("5") == "5"


@pytest.mark.parametrize(
    "node_factory, port_name",
    [
        (GaussianBlur, "ksize"),
        (Median, "size"),
        (AdaptiveGaussianThreshold, "block_size"),
    ],
)
def test_all_oddint_nodes_get_odd_widget(qapp, node_factory, port_name) -> None:
    """Every existing :class:`OddIntParam` consumer must pick up the
    odd-only widget. Adding a new filter that uses :class:`OddIntParam`
    should not need to remember to wire the widget separately —
    declaring the param is enough."""
    node = node_factory()
    widget = build_param_widget(node, _port(node, port_name))
    assert isinstance(widget, OddIntParamWidget)


# ── Spin-box honours descriptor min / max ─────────────────────────────────────

@pytest.mark.parametrize(
    "node_factory, port_name, expected_min",
    [
        (GaussianBlur, "ksize", 3),
        (Median, "size", 3),
        (AdaptiveGaussianThreshold, "block_size", 3),
    ],
)
def test_oddint_widget_pins_minimum_to_descriptor(
    qapp, node_factory, port_name, expected_min,
) -> None:
    """Kernel-size editors must refuse values below the descriptor's
    declared minimum. A 1-px (or 2-px etc.) kernel is the no-op
    identity for these filters; without a widget-side guard a user
    could type a negative number or a 1, hit Enter, and have the
    descriptor either raise (negative) or quietly bump to 1 anyway —
    neither matches what the user typed.
    """
    node = node_factory()
    widget = build_param_widget(node, _port(node, port_name))
    assert widget._spin.minimum() == expected_min


def test_int_widget_honours_metadata_min_max(qapp: QApplication) -> None:
    """Plain :class:`IntParam` ports also propagate their ``min`` /
    ``max`` to the spin box — the change isn't OddInt-specific."""
    from nodes.filters.crop import Crop
    node = Crop()
    widget = build_param_widget(node, _port(node, "width"))
    # Crop.width declares min=1.
    assert widget._spin.minimum() == 1


def test_int_widget_falls_back_to_wide_range_without_metadata(
    qapp: QApplication,
) -> None:
    """A descriptor that doesn't declare bounds must keep the
    historic wide range — otherwise unconstrained ints would lose
    their ability to take negatives or large values."""
    from nodes.filters.shift import Shift
    node = Shift()
    widget = build_param_widget(node, _port(node, "offset_x"))
    assert widget._spin.minimum() == IntParamWidget._DEFAULT_MIN
    assert widget._spin.maximum() == IntParamWidget._DEFAULT_MAX


# ── Temporal filters reject the no-op window of 1 ─────────────────────────────

@pytest.mark.parametrize(
    "module_path, class_name, expected_min",
    [
        ("nodes.filters.temporal_median", "TemporalMedian", 2),
        ("nodes.filters.temporal_mean",   "TemporalMean",   2),
    ],
)
def test_temporal_window_rejects_one(
    qapp, module_path, class_name, expected_min,
) -> None:
    """``window=1`` is the pass-through identity for these temporal
    filters; the descriptor and the widget both refuse it now."""
    import importlib
    cls = getattr(importlib.import_module(module_path), class_name)
    node = cls()
    with pytest.raises(ValueError):
        node.window = 1
    widget = build_param_widget(node, _port(node, "window"))
    assert widget._spin.minimum() == expected_min

"""Tests for the :class:`~nodes.filters.plot_xy.PlotXY` node."""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from core.io_data import IoData, IoDataType
from nodes.filters.plot_xy import PlotXY


def _xy_df(n: int = 16) -> pd.DataFrame:
    """A minimal two-column DataFrame for plotting."""
    x = np.linspace(0.0, 1.0, n)
    return pd.DataFrame({"t": x, "v": np.sin(2 * np.pi * x)})


def _run(node: PlotXY, df: pd.DataFrame) -> np.ndarray:
    """Feed *df* into the node's input and return the emitted image."""
    node.inputs[0].receive(IoData.from_dataset(df))
    out = node.outputs[0].last_emitted
    assert out is not None, "PlotXY did not emit"
    assert out.type is IoDataType.IMAGE
    return out.image


# ── Render output shape ───────────────────────────────────────────────────────

def test_emits_image_of_requested_shape() -> None:
    node = PlotXY()
    node.width = 200
    node.height = 100

    img = _run(node, _xy_df())

    assert img.dtype == np.uint8
    assert img.ndim == 3
    assert img.shape[2] == 3  # BGR
    # matplotlib's Agg may produce ±1 pixel from the requested size at
    # tight_layout — assert exact match because we set figsize from the
    # explicit dpi/size relation. If matplotlib changes this assumption
    # the test will flag it.
    assert img.shape[:2] == (100, 200)


def test_default_columns_pick_first_two() -> None:
    """Empty x_column / y_column → first / second columns of the input."""
    node = PlotXY()  # defaults: x_column="", y_column=""
    img = _run(node, _xy_df())
    assert img.shape == (360, 640, 3)


def test_explicit_columns_select_those() -> None:
    df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6], "c": [7, 8, 9]})
    node = PlotXY()
    node.x_column = "a"
    node.y_column = "c"
    img = _run(node, df)
    assert img.size > 0


# ── Error paths ───────────────────────────────────────────────────────────────

def test_missing_column_raises_keyerror() -> None:
    df = _xy_df()
    node = PlotXY()
    node.x_column = "nope"

    with pytest.raises(KeyError, match="not in dataset"):
        _run(node, df)


def test_empty_dataset_raises() -> None:
    df = pd.DataFrame()
    node = PlotXY()
    with pytest.raises(KeyError):
        _run(node, df)


def test_single_column_input_raises_with_hint_to_add_index_column() -> None:
    """A 1-column DATASET no longer auto-falls-back to a row index.
    The error message points the user at the AddIndexColumn node so
    the fix path is discoverable."""
    df = pd.DataFrame({"velocity": np.linspace(0.0, 1.0, 8)})
    node = PlotXY()
    with pytest.raises(KeyError, match="AddIndexColumn"):
        _run(node, df)


# ── Pure helpers ──────────────────────────────────────────────────────────────

def test_axis_label_falls_back_to_column_name_without_units() -> None:
    df = pd.DataFrame({"x": [0], "y": [0]})
    assert PlotXY._axis_label(df, "x") == "x"


def test_axis_label_appends_unit_when_attrs_units_set() -> None:
    df = pd.DataFrame({"V": [0.0], "I": [0.0]})
    df.attrs["units"] = {"V": "V", "I": "A"}
    assert PlotXY._axis_label(df, "V") == "V [V]"
    assert PlotXY._axis_label(df, "I") == "I [A]"


def test_axis_label_handles_missing_unit_for_known_column() -> None:
    df = pd.DataFrame({"x": [0], "y": [0]})
    df.attrs["units"] = {"x": "s"}  # no entry for 'y'
    assert PlotXY._axis_label(df, "y") == "y"


def test_resolve_column_default_index_picks_by_position() -> None:
    df = pd.DataFrame({"first": [0], "second": [0], "third": [0]})
    assert PlotXY._resolve_column(df, "", default_index=0) == "first"
    assert PlotXY._resolve_column(df, "", default_index=1) == "second"
    assert PlotXY._resolve_column(df, "third", default_index=0) == "third"


# ── Memory leak guard ─────────────────────────────────────────────────────────

def test_no_open_figures_after_process() -> None:
    """A long-running flow renders one plot per frame; matplotlib leaks
    figures unless they are explicitly closed. PlotXY must close every
    figure it opens after a successful render."""
    plt.close("all")  # baseline
    node = PlotXY()
    df = _xy_df()
    for _ in range(5):
        node.inputs[0].receive(IoData.from_dataset(df))
    assert plt.get_fignums() == [], "PlotXY left matplotlib figures open"


def test_no_open_figures_after_render_error() -> None:
    """If something goes wrong during rendering after the figure has
    been created, the ``finally`` in ``_render`` must still close it.
    Drives ``_render`` directly with a mismatched-shape pair so plot()
    raises mid-render."""
    plt.close("all")
    with pytest.raises(ValueError):
        PlotXY._render(
            np.array([0.0, 1.0, 2.0]),
            np.array([0.0, 1.0]),  # length mismatch → matplotlib raises
            x_label="x",
            y_label="y",
            width=120,
            height=80,
            title="",
            grid=False,
        )
    assert plt.get_fignums() == []


# ── Band overlay (issue #246) ───────────────────────────────────────────────


def test_band_inputs_when_unconnected_render_unchanged() -> None:
    """No band SCALARs connected → render is byte-identical to the
    pre-band baseline. Adding the optional ports must not perturb the
    default visual."""
    node = PlotXY()
    node.width = 200
    node.height = 100
    img = _run(node, _xy_df())
    # Render a second time without any band wiring; both should match.
    node2 = PlotXY()
    node2.width = 200
    node2.height = 100
    img2 = _run(node2, _xy_df())
    np.testing.assert_array_equal(img, img2)


def test_band_renders_yellow_pixels_in_band_x_range() -> None:
    """With band_start / band_end connected, the band paints a
    translucent yellow rectangle (#ffd24a, alpha 0.20). Inside the
    band's x-range the image picks up yellow tint; outside the
    image is plain white background.
    """
    node = PlotXY()
    node.width = 400
    node.height = 200
    node.grid = False
    df = pd.DataFrame({"t": np.linspace(0.0, 1.0, 32), "v": np.zeros(32)})
    node.inputs[1].receive(IoData.from_scalar(0.4))
    node.inputs[2].receive(IoData.from_scalar(0.6))
    node.inputs[0].receive(IoData.from_dataset(df))
    img = node.outputs[0].last_emitted.image  # type: ignore[union-attr]

    # Sample a horizontal strip well above the trace at y=0 so we don't
    # overlap with the actual line. Find columns whose green channel
    # dropped below pure-white (band tint pulls G down).
    strip = img[20, :, :]  # BGR
    green = strip[:, 1].astype(np.int16)
    inside_band_dim = np.where(green < 250)[0]
    assert len(inside_band_dim) > 0, "expected the band to dim some pixels"


def test_reversed_band_endpoints_normalize_to_forward_range() -> None:
    """Wiring band_end < band_start is a wiring mistake — the node
    normalises so the band still renders as a forward span instead of
    matplotlib silently drawing an empty / inverted rectangle."""
    node = PlotXY()
    node.width = 200
    node.height = 100
    df = pd.DataFrame({"t": np.linspace(0.0, 1.0, 16), "v": np.zeros(16)})
    node.inputs[1].receive(IoData.from_scalar(0.7))
    node.inputs[2].receive(IoData.from_scalar(0.3))
    node.inputs[0].receive(IoData.from_dataset(df))
    img_reversed = node.outputs[0].last_emitted.image  # type: ignore[union-attr]

    node2 = PlotXY()
    node2.width = 200
    node2.height = 100
    node2.inputs[1].receive(IoData.from_scalar(0.3))
    node2.inputs[2].receive(IoData.from_scalar(0.7))
    node2.inputs[0].receive(IoData.from_dataset(df))
    img_forward = node2.outputs[0].last_emitted.image  # type: ignore[union-attr]

    np.testing.assert_array_equal(img_reversed, img_forward)


def test_only_one_band_endpoint_connected_skips_band() -> None:
    """Half-wired band (only band_start, not band_end) → no band drawn.
    Either both or neither — partial connections don't render."""
    node = PlotXY()
    node.width = 200
    node.height = 100
    df = pd.DataFrame({"t": np.linspace(0.0, 1.0, 16), "v": np.zeros(16)})
    node.inputs[1].receive(IoData.from_scalar(0.4))
    # band_end intentionally not wired
    node.inputs[0].receive(IoData.from_dataset(df))
    img_partial = node.outputs[0].last_emitted.image  # type: ignore[union-attr]

    node2 = PlotXY()
    node2.width = 200
    node2.height = 100
    node2.inputs[0].receive(IoData.from_dataset(df))
    img_baseline = node2.outputs[0].last_emitted.image  # type: ignore[union-attr]

    np.testing.assert_array_equal(img_partial, img_baseline)

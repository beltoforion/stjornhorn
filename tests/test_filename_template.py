"""Tests for the filename templating engine."""
from __future__ import annotations

from pathlib import Path

from core.filename_template import expand


# ── Direct meta lookups ───────────────────────────────────────────────────────


def test_plain_template_no_tokens_passes_through() -> None:
    assert expand("static.png", {}) == "static.png"


def test_frame_index_resolves_from_meta() -> None:
    assert expand("frame_$frame_index$.png", {"frame_index": 7}) == "frame_7.png"


def test_unknown_token_is_preserved_literally() -> None:
    """A typo (or a token the user expects but no upstream stamps)
    survives in the rendered filename so the slip is visible — better
    than silently writing ``out_.png`` and overwriting on every frame."""
    assert expand("out_$nope$.png", {"frame_index": 1}) == "out_$nope$.png"


def test_known_but_none_value_renders_empty() -> None:
    """When a token's key IS in meta but the value is ``None`` (e.g. a
    source-less synthetic stream), expand to empty rather than the
    literal token. Keeps `$source_stem$` from polluting the filename
    of a RangeSource→FileSink chain."""
    assert expand("a$frame_index$b", {"frame_index": None}) == "ab"


# ── Width syntax ──────────────────────────────────────────────────────────────


def test_zero_pads_numeric_to_width() -> None:
    assert expand("$frame_index:4$", {"frame_index": 42}) == "0042"


def test_width_smaller_than_value_does_not_truncate() -> None:
    """Width is a minimum, not a maximum — counters that exceed it
    keep all their digits rather than silently overflowing."""
    assert expand("$frame_index:2$", {"frame_index": 999}) == "999"


def test_width_one_works() -> None:
    assert expand("$frame_index:1$", {"frame_index": 0}) == "0"


def test_width_pads_string_value() -> None:
    """Non-numeric values rj-pad with zeros so the width spec still has
    visible effect; rare but documented."""
    assert expand("$tag:5$", {"tag": "x"}) == "0000x"


def test_float_truncates_to_int_for_padding() -> None:
    """Frame counters can drift to float when increment is fractional;
    treat them as int for padding so the filename stays readable."""
    assert expand("$frame_index:3$", {"frame_index": 7.0}) == "007"


# ── Path-derived keys ─────────────────────────────────────────────────────────


def test_source_stem_from_pathlike() -> None:
    meta = {"source_path": Path("input/ship.jpg")}
    assert expand("$source_stem$.png", meta) == "ship.png"


def test_source_stem_from_string_path() -> None:
    """``source_path`` may be stored as a string in saved flows; the
    engine coerces."""
    meta = {"source_path": "/abs/path/ship.jpg"}
    assert expand("$source_stem$.png", meta) == "ship.png"


def test_source_name_includes_extension() -> None:
    meta = {"source_path": Path("ship.jpg")}
    assert expand("$source_name$", meta) == "ship.jpg"


def test_source_ext_drops_leading_dot() -> None:
    """``$source_ext$`` renders without the dot so users prepend their
    own (typical pattern: ``out.$source_ext$``)."""
    meta = {"source_path": Path("ship.jpg")}
    assert expand("$source_ext$", meta) == "jpg"
    assert expand("derived.$source_ext$", meta) == "derived.jpg"


def test_source_keys_unknown_when_no_source_path() -> None:
    """A synthetic stream (RangeSource, ConstantValue) has no
    source_path; ``$source_stem$`` then keeps its literal text."""
    assert expand("$source_stem$.png", {}) == "$source_stem$.png"


# ── Run-context keys ──────────────────────────────────────────────────────────


def test_context_resolves_flow_name() -> None:
    out = expand("$flow_name$.mp4", meta={}, context={"flow_name": "demo"})
    assert out == "demo.mp4"


def test_meta_takes_precedence_over_context() -> None:
    """If both meta and context define the same key, meta wins — the
    runner's bulk run_context is overridable by an upstream node that
    cares enough to stamp something different."""
    out = expand(
        "$flow_name$",
        meta={"flow_name": "from-meta"},
        context={"flow_name": "from-ctx"},
    )
    assert out == "from-meta"


def test_context_can_be_omitted() -> None:
    """The ``context`` argument is optional; meta-only callers don't
    have to plumb a placeholder."""
    assert expand("$frame_index$.txt", {"frame_index": 5}) == "5.txt"


# ── Multiple tokens in one template ───────────────────────────────────────────


def test_multiple_tokens_resolve_independently() -> None:
    meta = {
        "source_path": Path("input/ship.jpg"),
        "frame_index": 3,
    }
    out = expand("$source_stem$_frame$frame_index:4$.png", meta)
    assert out == "ship_frame0003.png"


def test_repeated_token_resolves_each_occurrence() -> None:
    out = expand("$frame_index$ and $frame_index$", {"frame_index": 7})
    assert out == "7 and 7"


# ── Edge cases ────────────────────────────────────────────────────────────────


def test_dollar_outside_token_pattern_passes_through() -> None:
    """A standalone ``$`` (no matching pair) is not a token — it's a
    literal character. Keep it as-is so users can write paths like
    ``cost_$$.txt`` if they want."""
    assert expand("plain$with no close", {}) == "plain$with no close"


def test_empty_template() -> None:
    assert expand("", {"frame_index": 1}) == ""


def test_token_with_only_underscores_and_digits() -> None:
    assert expand("$my_key_2$", {"my_key_2": "ok"}) == "ok"


def test_width_spec_zero_renders_value_unchanged() -> None:
    """Width 0 is degenerate but legal — formats as if no width given."""
    assert expand("$frame_index:0$", {"frame_index": 7}) == "7"

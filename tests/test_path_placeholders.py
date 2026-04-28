"""Unit tests for ``core.path_placeholders.expand_placeholders``. Issue #159."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from core.path_placeholders import (
    expand_placeholders,
    has_placeholders,
)


def test_no_placeholders_returns_template_verbatim() -> None:
    """Common case: a literal path string is returned byte-for-byte."""
    assert expand_placeholders("out.png") == "out.png"
    assert expand_placeholders("output/sub/out.mp4") == "output/sub/out.mp4"


def test_input_stem_expands_to_source_filename_without_extension() -> None:
    expanded = expand_placeholders(
        "$input_stem$.png", source_path=Path("/abs/path/ship.jpg"),
    )
    assert expanded == "ship.png"


def test_input_name_includes_extension() -> None:
    expanded = expand_placeholders(
        "copy_$input_name$", source_path=Path("ship.jpg"),
    )
    assert expanded == "copy_ship.jpg"


def test_input_ext_strips_leading_dot() -> None:
    assert expand_placeholders(
        "out.$input_ext$", source_path=Path("ship.JPG"),
    ) == "out.JPG"


def test_flow_name_expands() -> None:
    assert expand_placeholders(
        "$flow_name$.png", flow_name="denoise_v2",
    ) == "denoise_v2.png"


def test_frame_index_zero_padded_to_four_digits() -> None:
    assert expand_placeholders(
        "frame_$frame_index$.png", frame_index=0,
    ) == "frame_0000.png"
    assert expand_placeholders(
        "frame_$frame_index$.png", frame_index=42,
    ) == "frame_0042.png"
    assert expand_placeholders(
        "frame_$frame_index$.png", frame_index=12345,
    ) == "frame_12345.png"


def test_timestamp_uses_yyyymmdd_hhmmss() -> None:
    when = datetime(2026, 4, 28, 13, 45, 9)
    assert expand_placeholders(
        "run_$timestamp$.png", run_started_at=when,
    ) == "run_20260428_134509.png"


def test_combined_tokens() -> None:
    expanded = expand_placeholders(
        "$input_stem$.$flow_name$.frame_$frame_index$.$input_ext$",
        source_path=Path("ship.jpg"),
        flow_name="denoise",
        frame_index=7,
    )
    assert expanded == "ship.denoise.frame_0007.jpg"


def test_unknown_token_passes_through_unchanged() -> None:
    """A typo'd token is left as-is so the user spots it in the file
    name rather than getting a silent empty string."""
    assert expand_placeholders(
        "$nope$.png", source_path=Path("ship.jpg"),
    ) == "$nope$.png"


def test_unresolved_known_token_expands_to_empty_string() -> None:
    """Known tokens with no value collapse to ``""``. The user opted in
    to the placeholder; the empty string is at least a debuggable
    artefact in the resulting filename."""
    assert expand_placeholders("$input_stem$.png") == ".png"
    assert expand_placeholders("$flow_name$.png") == ".png"


def test_has_placeholders_true_for_token() -> None:
    assert has_placeholders("$input_stem$.png") is True
    assert has_placeholders("frame_$frame_index$.png") is True


def test_has_placeholders_false_for_literal() -> None:
    assert has_placeholders("out.png") is False
    # A lone ``$`` without a closing ``$`` doesn't match the token
    # pattern — the dollar sign is just a literal.
    assert has_placeholders("price_$5.png") is False

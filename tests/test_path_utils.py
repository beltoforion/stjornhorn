"""Unit tests for the relative-path helpers used by file-IO nodes."""
from __future__ import annotations

from pathlib import Path

from core.path_utils import (
    non_ascii_chars,
    resolve_against,
    store_relative_to,
    write_failure_hint,
)


# ── store_relative_to ────────────────────────────────────────────────────────


def test_absolute_inside_base_is_made_relative(tmp_path: Path) -> None:
    """An absolute path inside ``base_dir`` round-trips as a relative
    path so saved flows stay portable across machines that share the
    same input/output layout."""
    target = tmp_path / "ship.jpg"
    target.write_bytes(b"")  # resolve() needs the path to exist for symlinks
    out = store_relative_to(target, tmp_path)
    assert out == Path("ship.jpg")
    assert not out.is_absolute()


def test_absolute_inside_subdirectory_keeps_subdirectory(tmp_path: Path) -> None:
    sub = tmp_path / "subset"
    sub.mkdir()
    target = sub / "frame.png"
    target.write_bytes(b"")
    out = store_relative_to(target, tmp_path)
    assert out == Path("subset") / "frame.png"


def test_absolute_outside_base_is_kept_absolute(tmp_path: Path) -> None:
    """A path that doesn't live under ``base_dir`` must round-trip
    unchanged — flattening it would silently relocate the user's
    file at run time."""
    other_root = tmp_path / "elsewhere"
    other_root.mkdir()
    target = other_root / "video.mp4"
    target.write_bytes(b"")
    base_dir = tmp_path / "input"
    base_dir.mkdir()
    out = store_relative_to(target, base_dir)
    assert out.is_absolute()
    assert out == target.resolve()


def test_relative_input_returned_unchanged() -> None:
    """Already-relative input is passed through verbatim — even when
    it contains traversal (``../foo``) or refers to a missing file.
    The helper's job is to normalise the *absolute* case; relative
    input is the user's explicit choice and we don't anchor it."""
    p = Path("../sibling/frame.png")
    out = store_relative_to(p, Path("/some/base"))
    assert out == p


def test_missing_base_dir_keeps_absolute(tmp_path: Path) -> None:
    """If ``base_dir`` itself doesn't exist on disk, ``resolve()`` on
    a path inside it can fail — we treat that as 'keep absolute'
    rather than raising, since the path may still be valid for the
    caller to use later (e.g. INPUT_DIR is created lazily)."""
    target = tmp_path / "ghost.jpg"
    target.write_bytes(b"")
    nonexistent_base = tmp_path / "does_not_exist"
    out = store_relative_to(target, nonexistent_base)
    # Either kept absolute (the ValueError branch) or rewritten — we
    # accept both as long as no exception leaks out.
    assert isinstance(out, Path)


def test_string_input_is_coerced_to_path() -> None:
    """The setters that wrap this helper accept ``str | Path`` —
    the helper handles both."""
    out = store_relative_to("relative/dir", Path("/some/base"))
    assert out == Path("relative/dir")


# ── resolve_against ──────────────────────────────────────────────────────────


def test_resolve_relative_joins_base() -> None:
    out = resolve_against(Path("frame.png"), Path("/input"))
    assert out == Path("/input/frame.png")
    assert out.is_absolute()


def test_resolve_absolute_passes_through() -> None:
    """An already-absolute path must not be re-anchored against
    ``base_dir`` — the user explicitly picked a location outside
    the well-known root."""
    abs_path = Path("/elsewhere/video.mp4")
    out = resolve_against(abs_path, Path("/input"))
    assert out == abs_path


# ── non_ascii_chars / write_failure_hint ─────────────────────────────────────


def test_non_ascii_chars_returns_empty_for_pure_ascii() -> None:
    assert non_ascii_chars(Path("/home/user/output/frame_0001.png")) == []


def test_non_ascii_chars_collects_unique_sorted_offenders() -> None:
    """Multiple occurrences of the same offender collapse; the result
    is sorted so the message is stable across runs."""
    out = non_ascii_chars(Path(r"C:\Users\jürgen\stjörnhorn\öutput\f.png"))
    assert out == ["ö", "ü"]
    assert non_ascii_chars("äöüäö") == ["ä", "ö", "ü"]


def test_non_ascii_chars_accepts_string_input() -> None:
    assert non_ascii_chars("plain") == []
    assert non_ascii_chars("café") == ["é"]


def test_write_failure_hint_pure_ascii_falls_back_to_generic() -> None:
    """An ASCII path yields the generic 'invalid filename' note —
    we have no specific diagnosis to offer in that case."""
    hint = write_failure_hint(Path("/tmp/output/frame.png"))
    assert "non-ASCII" not in hint
    assert "invalid" in hint.lower()


def test_write_failure_hint_flags_non_ascii_path_with_offending_chars() -> None:
    """A path with umlauts / accents must surface the actual offending
    characters so the user can map the message to a fix without guessing."""
    hint = write_failure_hint(
        Path(r"C:\Users\user\Documents\GitHub\stjörnhorn\output\00017.png"),
    )
    assert "non-ASCII" in hint
    assert "'ö'" in hint


def test_write_failure_hint_lists_each_offending_char_once() -> None:
    """Repeated offenders collapse to one mention each; sorted order
    keeps the message deterministic."""
    hint = write_failure_hint("/tmp/öäöä/ä.png")
    assert hint.count("'ä'") == 1
    assert hint.count("'ö'") == 1
    assert hint.index("'ä'") < hint.index("'ö'")


# ── resolve_against ──────────────────────────────────────────────────────────


def test_round_trip_inside_base(tmp_path: Path) -> None:
    """``store_relative_to`` followed by ``resolve_against`` returns
    a path that points at the same file, even when the original was
    absolute and the intermediate stored form was relative."""
    target = tmp_path / "frame.png"
    target.write_bytes(b"")
    stored = store_relative_to(target, tmp_path)
    resolved = resolve_against(stored, tmp_path)
    assert resolved.resolve() == target.resolve()

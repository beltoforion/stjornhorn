"""Helpers for the relative-path normalisation that file-IO nodes share.

Five nodes (``ImageSource`` / ``VideoSource`` / ``DirectorySource`` /
``FileSink`` / ``VideoSink``) all want the same trick: when the user
picks a path inside a "well-known" base directory (``INPUT_DIR`` for
sources, ``OUTPUT_DIR`` for sinks), persist it relative to that base
so saved flows stay portable across machines that share the same
input / output layout — but keep paths outside the base absolute, so
arbitrary user files still round-trip. This module is the single
source of truth for that policy; each node passes its own base dir.
"""
from __future__ import annotations

from pathlib import Path


def store_relative_to(value: str | Path, base_dir: Path) -> Path:
    """Return *value* as a :class:`Path`, rewriting it as a path
    relative to ``base_dir`` whenever it lives inside that directory.

    Behaviour:
      * Absolute paths inside ``base_dir`` → relative to ``base_dir``.
      * Absolute paths outside ``base_dir`` → kept absolute.
      * Already-relative paths → returned unchanged (no
        ``base_dir`` poke; the path may legitimately reach outside
        the dev tree via ``../foo`` and we don't want to anchor it).

    The relative-isation goes through :meth:`Path.resolve` so symlinks
    and ``..`` segments are normalised before the comparison; ``OSError``
    (a missing intermediate directory) and ``ValueError`` (the resolved
    target is genuinely outside ``base_dir``) are both treated as
    "keep the absolute form" rather than failures, since the path may
    still be perfectly valid for the node to read / write later.
    """
    p = Path(value)
    if not p.is_absolute():
        return p
    try:
        return p.resolve().relative_to(base_dir.resolve())
    except (OSError, ValueError):
        return p


def resolve_against(path: Path, base_dir: Path) -> Path:
    """Return an absolute :class:`Path` for *path*.

    Joins ``base_dir`` for relative inputs (so a flow stored with
    ``"video.mp4"`` resolves to ``INPUT_DIR / "video.mp4"`` at run
    time); passes absolute inputs through unchanged.
    """
    if path.is_absolute():
        return path
    return base_dir / path


_GENERIC_WRITE_HINT = (
    "This often means the rendered filename/path is invalid for the "
    "current OS."
)


def non_ascii_chars(path: Path | str) -> list[str]:
    """Return the sorted, de-duplicated non-ASCII characters in *path*."""
    return sorted({c for c in str(path) if ord(c) > 127})


def write_failure_hint(path: Path | str) -> str:
    """Diagnostic hint for OpenCV file-write failures on *path*.

    OpenCV's writers (``cv2.imwrite``, ``cv2.VideoWriter``) on Windows
    route through the C runtime's ANSI ``fopen``, which silently fails
    on any path containing characters outside the active code page —
    most commonly umlauts and accented letters in the user profile or
    project directory. The sinks call this helper to turn that opaque
    failure into an actionable error message; if the path is plain
    ASCII, the generic 'invalid filename' note is returned instead.
    """
    bad = non_ascii_chars(path)
    if not bad:
        return _GENERIC_WRITE_HINT
    rendered = ", ".join(f"'{c}'" for c in bad)
    return (
        f"The path contains non-ASCII characters ({rendered}) — OpenCV's "
        "file writer uses the C runtime's ANSI encoding on Windows and "
        "silently fails on umlauts / accented letters. Move the output "
        "directory to an ASCII-only path."
    )

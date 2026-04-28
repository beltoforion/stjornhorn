"""Output-path placeholder expansion for sinks.

Sink nodes (``FileSink``, ``VideoSink``) accept ``$token$`` placeholders
in their ``output_path`` so the on-disk filename can be derived from the
input flowing through the flow. See issue #159.

Supported tokens:

==================  =============================================
``$input_stem$``    Filename (no extension) of the originating
                    source, e.g. ``ship`` for ``ship.jpg``.
``$input_name$``    Filename with extension, e.g. ``ship.jpg``.
``$input_ext$``     Extension without the dot, e.g. ``jpg``.
``$flow_name$``     Name of the currently-loaded flow.
``$frame_index$``   Zero-padded running frame index (``0001``).
``$timestamp$``     Run start time as ``YYYYMMDD_HHMMSS``.
==================  =============================================

Placeholders that can't be resolved (e.g. ``$input_stem$`` when no
source has stamped a path) expand to an empty string. Tokens that don't
match any of the above are passed through unchanged.

A path with no placeholders is returned as-is, byte-for-byte — keeps
the common case (a literal ``out.png``) backwards-compatible.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

#: Matches a ``$token$`` token. The inner group is the token name.
_PLACEHOLDER_RE = re.compile(r"\$([a-zA-Z_][a-zA-Z0-9_]*)\$")

#: Default zero-padding width for ``$frame_index$``.
FRAME_INDEX_WIDTH: int = 4


def has_placeholders(template: str) -> bool:
    """Return True if ``template`` contains at least one ``$token$``."""
    return _PLACEHOLDER_RE.search(template) is not None


def expand_placeholders(
    template: str,
    *,
    source_path: Path | None = None,
    flow_name: str | None = None,
    frame_index: int | None = None,
    run_started_at: datetime | None = None,
) -> str:
    """Expand ``$token$`` placeholders in ``template``.

    Args:
        template: The user-supplied path string (relative or absolute).
        source_path: Originating filename of the upstream source, if known.
        flow_name: Name of the currently-running flow, if known.
        frame_index: Running per-frame counter for streaming sinks.
        run_started_at: Run start time, used by ``$timestamp$``.

    Returns:
        The expanded path string. Unknown tokens are left untouched so
        the user can spot typos by reading the resulting filename.
    """
    if not has_placeholders(template):
        return template

    values: dict[str, str] = {}

    if source_path is not None:
        values["input_name"] = source_path.name
        values["input_stem"] = source_path.stem
        # Path.suffix includes the leading dot; strip it for the token.
        values["input_ext"] = source_path.suffix.lstrip(".")
    else:
        values["input_name"] = ""
        values["input_stem"] = ""
        values["input_ext"] = ""

    values["flow_name"] = flow_name or ""

    if frame_index is not None:
        values["frame_index"] = f"{frame_index:0{FRAME_INDEX_WIDTH}d}"
    else:
        values["frame_index"] = ""

    if run_started_at is not None:
        values["timestamp"] = run_started_at.strftime("%Y%m%d_%H%M%S")
    else:
        values["timestamp"] = ""

    def _sub(match: re.Match[str]) -> str:
        token = match.group(1)
        if token in values:
            return values[token]
        # Unknown token: pass the literal ``$token$`` through unchanged.
        return match.group(0)

    return _PLACEHOLDER_RE.sub(_sub, template)

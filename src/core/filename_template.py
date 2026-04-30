"""Filename templating from :class:`~core.io_data.IoMeta`.

A small parser that expands ``$token$`` placeholders in an output-path
template against an :class:`~core.io_data.IoMeta`-style mapping plus an
optional run-context mapping. Produces a concrete filename per write.

Token grammar
-------------

Each placeholder is delimited by ``$`` on both sides::

    $name$           literal lookup; renders the value as-is
    $name:N$         numeric lookup, zero-padded to N characters

Examples:

- ``out_$frame_index:4$.png``  →  ``out_0042.png`` (when frame_index=42)
- ``$source_stem$.processed.png``  →  ``ship.processed.png``
  (when source_path=PosixPath('input/ship.jpg'))
- ``$flow_name$_$timestamp$.mp4``  →  ``data_display_20260430_153012.mp4``

Conventions
-----------

The engine resolves three kinds of keys:

1. **Direct meta keys** (``frame_index``, ``timestamp``, …) — looked up
   on the supplied meta mapping verbatim.
2. **Path-derived keys** (``source_stem``, ``source_name``,
   ``source_ext``) — derived from ``meta["source_path"]`` if present.
3. **Run-context keys** (``flow_name``) — looked up on a separate
   context mapping the runner / sink injects.

Unknown tokens are left as the literal placeholder text rather than
raising, so a typo doesn't abort a long run; the output filename
surfaces the unfilled ``$tok$`` so the user sees the slip when they
look at the file.

Tokens that resolve to ``None`` (e.g. ``$source_stem$`` when no
source_path was stamped) render as the empty string.

Stateless & pure: every call is a fresh expansion with no hidden
dependencies. Safe to invoke from worker or UI thread.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping


#: Matches a single ``$name$`` or ``$name:width$`` placeholder.
#:
#: ``name`` is one or more ``[A-Za-z0-9_]`` characters (no inner
#: dollar). ``width`` is one or more digits. Anchored neither at start
#: nor end so a template can hold many placeholders.
_TOKEN_RE = re.compile(
    r"\$(?P<name>[A-Za-z0-9_]+)(?::(?P<width>\d+))?\$"
)


def expand(
    template: str,
    meta: Mapping[str, Any],
    context: Mapping[str, Any] | None = None,
) -> str:
    """Resolve ``$token$`` placeholders in *template* against *meta*
    (and optional *context*) and return the expanded string.

    Unknown tokens are preserved as their literal placeholder. Tokens
    whose resolved value is ``None`` expand to the empty string.

    Width-suffixed tokens (``$frame_index:4$``) zero-pad the numeric
    representation; a non-numeric value is rendered as ``str(value)``
    and right-aligned with leading zeros if it's shorter than width
    (rare; mostly relevant for integer counters).
    """
    ctx = context if context is not None else {}

    def _resolve(match: re.Match[str]) -> str:
        name = match.group("name")
        width_str = match.group("width")
        value = _lookup(name, meta, ctx)
        if value is None:
            return match.group(0) if name not in _KNOWN_KEYS(meta, ctx) else ""
        return _format(value, width_str)

    return _TOKEN_RE.sub(_resolve, template)


def _lookup(name: str, meta: Mapping[str, Any], ctx: Mapping[str, Any]) -> Any:
    """Resolve a single token name to a value (or ``None`` if unknown)."""
    # Direct meta hit wins — covers frame_index, timestamp, plus any
    # node-stamped custom key.
    if name in meta:
        return meta[name]

    # Path-derived shortcuts: user types $source_stem$, we look at
    # meta["source_path"] and pick the relevant attribute.
    source_path = meta.get("source_path")
    if source_path is not None:
        path = Path(source_path)
        if name == "source_stem":
            return path.stem
        if name == "source_name":
            return path.name
        if name == "source_ext":
            # Drop the leading dot so $source_ext$ → "jpg" not ".jpg";
            # users want to drop it into a filename and prepend their
            # own dot if they need one.
            return path.suffix.lstrip(".")

    # Fall back to run context (flow_name, run-level timestamp, …).
    if name in ctx:
        return ctx[name]

    return None


def _KNOWN_KEYS(meta: Mapping[str, Any], ctx: Mapping[str, Any]) -> set[str]:
    """Return the set of token names that this expansion COULD resolve.

    Used to distinguish "known token, value happens to be None"
    (render as empty string) from "totally unknown token" (preserve
    the literal placeholder so the user sees their typo).
    """
    keys: set[str] = set(meta.keys()) | set(ctx.keys())
    if "source_path" in meta:
        keys |= {"source_stem", "source_name", "source_ext"}
    return keys


def _format(value: Any, width_str: str | None) -> str:
    """Render *value* as a string, optionally zero-padded to *width*."""
    if width_str is None:
        return str(value)
    width = int(width_str)
    # Numeric values get integer-style zero padding; non-numeric fall
    # back to a right-aligned string fill so width still has a visible
    # effect (rare, but better than silently ignoring the spec).
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        # Truncate floats to int for padding — the use case is frame
        # counters, not currency.
        return f"{int(value):0{width}d}"
    return str(value).rjust(width, "0")

"""Persist and restore the node-palette section expand/collapse state.

Saves a small ``{section_name: expanded}`` map to a JSON file under
:data:`~constants.USER_CONFIG_DIR`. The file is human-readable for
debugging and versioned so future shape changes can invalidate stale
entries cleanly. Corrupt or missing files fall back to the default
(all sections expanded).

Issue: #190
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from constants import USER_CONFIG_DIR

logger = logging.getLogger(__name__)

NODE_LIST_STATE_FILE: Path = USER_CONFIG_DIR / "node_list_state.json"

_STATE_VERSION: int = 1


def save_node_list_state(
    states: dict[str, bool],
    path: Path = NODE_LIST_STATE_FILE,
) -> None:
    """Write the section expand/collapse map *states* to *path*."""
    payload = {"version": _STATE_VERSION, "sections": states}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError:
        logger.exception("Failed to save node-list state to %s", path)


def restore_node_list_state(
    path: Path = NODE_LIST_STATE_FILE,
) -> dict[str, bool] | None:
    """Load the section expand/collapse map from *path*.

    Returns ``None`` on any failure (missing file, version mismatch,
    corrupt JSON) so the caller can keep its defaults.
    """
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.exception("Failed to read node-list state from %s", path)
        return None
    if not isinstance(data, dict) or data.get("version") != _STATE_VERSION:
        logger.info(
            "Ignoring %s: unsupported version %r",
            path,
            data.get("version") if isinstance(data, dict) else None,
        )
        return None
    sections = data.get("sections")
    if not isinstance(sections, dict):
        return None
    return {k: bool(v) for k, v in sections.items() if isinstance(k, str)}

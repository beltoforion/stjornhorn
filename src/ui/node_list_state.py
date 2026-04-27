"""Persist and restore the node-palette section expand/collapse state.

Stores a small ``{section_name: expanded}`` map as a human-readable JSON
file under :data:`USER_CONFIG_DIR`, mirroring the ``recent_flows.json``
pattern already in use.  Each call to :func:`restore_node_list_state` is
a no-op when the file is absent or unreadable so first-run behaviour
(all sections expanded) is preserved automatically.

Issue: #190
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from constants import USER_CONFIG_DIR

if TYPE_CHECKING:
    from ui.node_list import NodeList

logger = logging.getLogger(__name__)

#: JSON file holding the persisted palette section state.  Sits next to
#: ``dock_layout.json`` so all editor-window persistence shares one directory.
NODE_LIST_STATE_FILE: Path = USER_CONFIG_DIR / "node_list_state.json"


def save_node_list_state(node_list: NodeList, path: Path = NODE_LIST_STATE_FILE) -> None:
    """Write the section expand/collapse state of *node_list* to *path*."""
    state = node_list.get_section_states()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except OSError:
        logger.exception("Failed to save node list state to %s", path)


def restore_node_list_state(node_list: NodeList, path: Path = NODE_LIST_STATE_FILE) -> bool:
    """Apply a previously saved section state to *node_list*.

    Returns ``True`` on success.  Missing, corrupt, or wrongly-typed files
    are silently ignored and the current expand/collapse state is left
    unchanged (defaults: all sections expanded).
    """
    if not path.exists():
        return False
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.exception("Failed to read node list state from %s", path)
        return False
    if not isinstance(raw, dict):
        logger.info("Ignoring %s: unexpected format", path)
        return False
    node_list.restore_section_states(raw)
    return True

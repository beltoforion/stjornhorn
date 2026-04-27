"""Persist and restore the editor's dock arrangement across sessions.

Wraps :meth:`QMainWindow.saveState` / :meth:`restoreState` in a JSON
file (base64-encoded byte array) under :data:`USER_CONFIG_DIR`. Versioned
so future layout changes can invalidate stale files cleanly. Corrupt or
unreadable files fall back to whatever defaults the caller has already
applied.

Issue: #183
"""
from __future__ import annotations

import base64
import binascii
import json
import logging
from pathlib import Path

from PySide6.QtCore import QByteArray
from PySide6.QtWidgets import QMainWindow

from constants import USER_CONFIG_DIR

logger = logging.getLogger(__name__)

#: JSON file holding the persisted dock layout. Sits next to
#: ``recent_flows.json`` so all editor-window persistence shares one
#: directory.
DOCK_LAYOUT_FILE: Path = USER_CONFIG_DIR / "dock_layout.json"

#: Bumped whenever the on-disk shape changes in a way restoreState can't
#: silently round-trip (e.g. a dock objectName is renamed). Old payloads
#: with a different version are ignored on load.
_LAYOUT_VERSION: int = 1


def save_dock_layout(window: QMainWindow, path: Path = DOCK_LAYOUT_FILE) -> None:
    """Write *window*'s dock + toolbar arrangement to *path*."""
    blob = bytes(window.saveState(_LAYOUT_VERSION))
    payload = {
        "version": _LAYOUT_VERSION,
        "state": base64.b64encode(blob).decode("ascii"),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError:
        logger.exception("Failed to save dock layout to %s", path)


def restore_dock_layout(window: QMainWindow, path: Path = DOCK_LAYOUT_FILE) -> bool:
    """Apply a previously persisted layout to *window*.

    Returns ``True`` when a layout was successfully restored. Returns
    ``False`` for any non-fatal failure (missing file, version mismatch,
    decode error, restoreState reject) so the caller can keep the
    defaults it already applied.
    """
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.exception("Failed to read dock layout from %s", path)
        return False
    if not isinstance(data, dict) or data.get("version") != _LAYOUT_VERSION:
        logger.info(
            "Ignoring %s: unsupported version %r",
            path, data.get("version") if isinstance(data, dict) else None,
        )
        return False
    encoded = data.get("state")
    if not isinstance(encoded, str):
        return False
    try:
        blob = base64.b64decode(encoded.encode("ascii"), validate=True)
    except (ValueError, binascii.Error):
        logger.exception("Failed to decode dock layout payload in %s", path)
        return False
    return window.restoreState(QByteArray(blob), _LAYOUT_VERSION)

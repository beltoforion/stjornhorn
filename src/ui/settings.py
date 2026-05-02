"""Persistent application settings.

The :class:`AppSettings` singleton loads and saves a small JSON file at
``~/.image-inquest/settings.json`` (or its frozen-build equivalent).
Mutating a setting writes the file immediately and emits a Qt signal so
interested parties (logging, UI) can react.

Today the only setting is :attr:`debug_logging`, which controls whether
the file log handler captures DEBUG records or only INFO and above.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from constants import USER_CONFIG_DIR

logger = logging.getLogger(__name__)

SETTINGS_FILE: Path = USER_CONFIG_DIR / "settings.json"

_SETTINGS_VERSION: int = 1

_DEFAULT_DEBUG_LOGGING: bool = False
_DEFAULT_PORT_LEGEND_VISIBLE: bool = True


def _read_settings_file(path: Path) -> dict:
    """Return the raw settings dict from *path*, or ``{}`` if unusable.

    Used both by :class:`AppSettings` and by early-startup code that
    needs a value before a :class:`QApplication` exists (e.g. the
    logging configuration).
    """
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.exception("Failed to read %s; using defaults", path)
        return {}
    if not isinstance(data, dict) or data.get("version") != _SETTINGS_VERSION:
        return {}
    return data


def read_debug_logging(path: Path = SETTINGS_FILE) -> bool:
    """Return the persisted ``debug_logging`` flag without instantiating Qt."""
    return bool(_read_settings_file(path).get("debug_logging", _DEFAULT_DEBUG_LOGGING))


class AppSettings(QObject):
    """Process-wide user settings, persisted to a JSON file.

    Use :func:`get_settings` to obtain the shared instance.
    """

    debug_logging_changed = Signal(bool)
    port_legend_visible_changed = Signal(bool)

    def __init__(self, path: Path = SETTINGS_FILE) -> None:
        super().__init__()
        self._path = path
        data = _read_settings_file(path)
        self._debug_logging: bool = bool(
            data.get("debug_logging", _DEFAULT_DEBUG_LOGGING)
        )
        self._port_legend_visible: bool = bool(
            data.get("port_legend_visible", _DEFAULT_PORT_LEGEND_VISIBLE)
        )

    # ── Access ────────────────────────────────────────────────────────────────

    @property
    def debug_logging(self) -> bool:
        return self._debug_logging

    @debug_logging.setter
    def debug_logging(self, value: bool) -> None:
        value = bool(value)
        if value == self._debug_logging:
            return
        self._debug_logging = value
        self._save()
        self.debug_logging_changed.emit(value)

    @property
    def port_legend_visible(self) -> bool:
        return self._port_legend_visible

    @port_legend_visible.setter
    def port_legend_visible(self, value: bool) -> None:
        value = bool(value)
        if value == self._port_legend_visible:
            return
        self._port_legend_visible = value
        self._save()
        self.port_legend_visible_changed.emit(value)

    # ── Persistence ───────────────────────────────────────────────────────────

    def _save(self) -> None:
        payload = {
            "version": _SETTINGS_VERSION,
            "debug_logging": self._debug_logging,
            "port_legend_visible": self._port_legend_visible,
        }
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError:
            logger.exception("Failed to save %s", self._path)


_INSTANCE: AppSettings | None = None


def get_settings() -> AppSettings:
    """Return the process-wide :class:`AppSettings` singleton."""
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = AppSettings()
    return _INSTANCE

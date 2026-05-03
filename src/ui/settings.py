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
#: Default theme key. ``ui.theme`` resolves the name against
#: :data:`ui.theme.AVAILABLE_THEMES` at module-import time, so an
#: unrecognised value silently falls back to the registered default.
#: The string lives here (rather than as a ``ui.theme`` import) to
#: keep ``ui.settings`` independent of the Qt-aware theme module.
_DEFAULT_THEME_NAME: str = "neon"


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
    #: Emitted when the user picks a different theme on the Settings
    #: page. The change only takes visual effect on next launch — the
    #: theme is locked at ``ui.theme`` import time, so consumers
    #: don't need to react beyond optionally surfacing a "restart to
    #: apply" hint.
    theme_name_changed = Signal(str)

    def __init__(self, path: Path = SETTINGS_FILE) -> None:
        super().__init__()
        self._path = path
        data = _read_settings_file(path)
        self._debug_logging: bool = bool(
            data.get("debug_logging", _DEFAULT_DEBUG_LOGGING)
        )
        raw_theme = data.get("theme_name", _DEFAULT_THEME_NAME)
        self._theme_name: str = (
            raw_theme if isinstance(raw_theme, str) else _DEFAULT_THEME_NAME
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
    def theme_name(self) -> str:
        return self._theme_name

    @theme_name.setter
    def theme_name(self, value: str) -> None:
        if not isinstance(value, str) or value == self._theme_name:
            return
        self._theme_name = value
        self._save()
        self.theme_name_changed.emit(value)

    # ── Persistence ───────────────────────────────────────────────────────────

    def _save(self) -> None:
        payload = {
            "version": _SETTINGS_VERSION,
            "debug_logging": self._debug_logging,
            "theme_name": self._theme_name,
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

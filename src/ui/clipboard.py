"""Centralised clipboard write helpers for the Qt UI.

All copy-to-clipboard call sites should funnel through this module so
that the ``QGuiApplication.clipboard()`` lookup, its ``None`` guard,
the ``numpy → QImage`` conversion and the user-visible feedback stay
consistent across the app. Extending the behaviour (e.g. propagating
to MIME data, supporting a secondary selection on X11, adding a
visual flash) becomes a single edit instead of a hunt through every
caller.
"""

from __future__ import annotations

import logging

import numpy as np
from PySide6.QtGui import QGuiApplication

from core import notifications

logger = logging.getLogger(__name__)


def copy_text(text: str) -> bool:
    """Push *text* onto the system clipboard.

    Returns ``True`` if the clipboard was written, ``False`` when no
    clipboard is available (headless environments, early startup
    before ``QGuiApplication`` has a chance to materialise one). Does
    not emit a notification — leave that to the caller so UI surfaces
    that already give feedback (e.g. the message banner the user just
    clicked) don't clobber themselves.
    """
    clipboard = QGuiApplication.clipboard()
    if clipboard is None:
        return False
    clipboard.setText(text)
    return True


def copy_image(frame: np.ndarray) -> bool:
    """Push *frame* onto the system clipboard as a ``QImage``.

    Returns ``True`` on success, ``False`` if the clipboard is
    unavailable or the array could not be converted. Conversion
    failures are logged and reported via :mod:`notifications` so the
    user gets a warning instead of a silent miss; callers do not need
    their own try/except.
    """
    clipboard = QGuiApplication.clipboard()
    if clipboard is None:
        return False
    # Local import: ``ui.preview_widgets`` pulls in OpenCV / heavy Qt
    # widget code that text-only callers (the message banner) do not
    # need at import time.
    from ui.preview_widgets import numpy_to_qimage

    try:
        qimg = numpy_to_qimage(frame)
    except Exception as exc:
        logger.exception("Clipboard: numpy → QImage conversion failed")
        notifications.warn(f"Could not copy image: {exc}")
        return False
    clipboard.setImage(qimg)
    return True


def dispatch_command_result(result: object) -> None:
    """Send a node :class:`Command` handler's return value to the
    clipboard.

    - ``str`` (non-empty) → text + "Copied to clipboard" notification.
    - :class:`numpy.ndarray` → image + "Image copied to clipboard"
      notification.
    - falsy (``None``, ``""``) or any other type → silent no-op so a
      header click costs nothing when there is nothing to copy yet.
    """
    if isinstance(result, str):
        if not result:
            return
        if copy_text(result):
            notifications.info("Copied to clipboard")
        return
    if isinstance(result, np.ndarray):
        if copy_image(result):
            notifications.info("Image copied to clipboard")
        return

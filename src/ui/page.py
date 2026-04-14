from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

if TYPE_CHECKING:
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QMenu


class Page(QWidget):
    """Base class for every top-level page stacked inside MainWindow.

    A page owns a QWidget body (populated by the subclass) and optionally
    a list of QMenus that the host main-window installs on the global
    menu bar while the page is active, and removes when the page is
    deactivated.

    The :attr:`title_changed` signal lets a page request that the main
    window update the window title without knowing about the main window
    directly.

    Subclasses should:

    * build their widgets in ``__init__`` via a normal layout call,
    * return their per-page menus from :meth:`page_menus`,
    * emit :attr:`title_changed` whenever their context (e.g. current
      flow name) changes.
    """

    title_changed = Signal(str)

    def page_menus(self) -> list[QMenu]:
        """Return the menus this page contributes to the global menu bar.

        Default: empty. Override to attach Save/Run/etc. to the
        application menu bar while the page is active.
        """
        return []

    def page_actions(self) -> list[QAction]:
        """Optional list of toolbar actions the page contributes.

        Default: empty. MainWindow does not yet use this, but it keeps
        the door open for shared toolbar slots.
        """
        return []

    def page_title(self) -> str:
        """Human-readable page title used in the window caption."""
        return ""

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def on_activated(self) -> None:
        """Called by MainWindow immediately after the page is made visible."""

    def on_deactivated(self) -> None:
        """Called by MainWindow just before another page becomes visible."""

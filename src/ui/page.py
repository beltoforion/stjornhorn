from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget

if TYPE_CHECKING:
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QMenu


class PageBase(QWidget):
    """Abstract base class for every top-level page stacked inside MainWindow.

    A page owns a QWidget body (populated by the subclass) and optionally
    contributes:

    * a list of QMenus installed on the global menu bar while the page
      is active (see :meth:`page_menus`), and
    * a list of QActions installed on the application toolbar next to
      the page-selector radio group (see :meth:`page_toolbar_actions`).

    The :attr:`title_changed` signal lets a page request that the main
    window update the window title without knowing about the main window
    directly.

    Subclasses must implement:

    * :meth:`page_selector_label` — terse label for the selector button,
    * :meth:`page_selector_icon` — icon for the selector button.

    Subclasses should also:

    * build their widgets in ``__init__`` via a normal layout call,
    * return their per-page menus from :meth:`page_menus`,
    * return their per-page toolbar items from :meth:`page_toolbar_actions`,
    * emit :attr:`title_changed` whenever their context (e.g. current
      flow name) changes.

    Note: this class cannot use ``_WidgetMeta`` (the combined Qt+ABCMeta
    metaclass) because PySide6's Shiboken metaclass deadlocks when
    ABCMeta is mixed with ``Signal`` descriptors. The abstract interface
    is enforced via ``NotImplementedError`` instead.
    """

    title_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        if type(self) is PageBase:
            raise TypeError("PageBase cannot be instantiated directly")
        super().__init__(parent)

    # ── Abstract interface ─────────────────────────────────────────────────────

    def page_selector_label(self) -> str:
        """Short label for the page-selector radio group."""
        raise NotImplementedError

    def page_selector_icon(self) -> QIcon:
        """Icon for the page-selector radio group."""
        raise NotImplementedError

    # ── Concrete defaults ──────────────────────────────────────────────────────

    def page_menus(self) -> list[QMenu]:
        """Return the menus this page contributes to the global menu bar.

        Default: empty. Override to attach Save/Run/etc. to the
        application menu bar while the page is active.
        """
        return []

    def page_toolbar_actions(self) -> list[QAction]:
        """Return the actions this page contributes to the main toolbar.

        MainWindow installs these next to the page-selector radio group
        while the page is active and removes them when the page is
        deactivated. Default: empty.
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

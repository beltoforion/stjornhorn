from __future__ import annotations

from typing import NamedTuple, TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QWidget

from ui.app_version_status_widget import AppVersionStatusWidget

if TYPE_CHECKING:
    from PySide6.QtWidgets import QMenu


class ToolbarSection(NamedTuple):
    """A named group of toolbar actions separated by a divider."""
    name: str
    actions: list[QAction]


class PageBase(QWidget):
    """Abstract base class for every top-level page stacked inside MainWindow.

    A page owns a QWidget body (populated by the subclass) and optionally
    contributes:

    * a list of QMenus installed on the global menu bar while the page
      is active (see :meth:`page_menus`), and
    * a list of QActions installed on the application toolbar next to
      the page-selector radio group (see :meth:`page_toolbar_actions`), and
    * a status widget anchored to the right of the main toolbar (see
      :meth:`page_status_widget`), used to surface page-specific state
      such as a running-flow indicator.

    The :attr:`title_changed` signal lets a page request that the main
    window update the window title without knowing about the main window
    directly. :attr:`status_widget_changed` asks MainWindow to re-install
    the page's status widget on the toolbar — use it when the page wants
    to swap widgets (e.g. from an idle label to a busy spinner) without
    waiting for the next page switch.

    Subclasses must implement:

    * :meth:`page_selector_label` — terse label for the selector button,
    * :meth:`page_selector_icon` — icon for the selector button.

    Subclasses should also:

    * build their widgets in ``__init__`` via a normal layout call,
    * return their per-page menus from :meth:`page_menus`,
    * return their per-page toolbar items from :meth:`page_toolbar_actions`,
    * emit :attr:`title_changed` whenever their context (e.g. current
      flow name) changes.

    """

    title_changed = Signal(str)
    status_widget_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        if type(self) is PageBase:
            raise TypeError("PageBase cannot be instantiated directly")
        super().__init__(parent)
        self._default_status_widget: AppVersionStatusWidget | None = None

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

    def page_toolbar_sections(self) -> list[ToolbarSection]:
        """Return named groups of actions for the main toolbar.

        MainWindow installs these next to the page-selector radio group
        while the page is active and removes them when the page is
        deactivated. Each section is separated by a divider.
        Default: empty.
        """
        return []

    def page_status_widget(self) -> QWidget | None:
        """Return the widget MainWindow should pin to the far right of the toolbar.

        Default: an :class:`AppVersionStatusWidget` showing the app name and
        version, so every page has a sensible right-edge affordance without
        boilerplate. Pages that want dynamic state (a progress spinner, a
        connection light, …) override this and emit
        :attr:`status_widget_changed` whenever the returned widget needs to
        be swapped for a different one.
        """
        if self._default_status_widget is None:
            self._default_status_widget = AppVersionStatusWidget()
        return self._default_status_widget

    def page_title(self) -> str:
        """Human-readable page title used in the window caption."""
        return ""

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def on_activated(self) -> None:
        """Called by MainWindow immediately after the page is made visible."""

    def on_deactivated(self) -> None:
        """Called by MainWindow just before another page becomes visible."""

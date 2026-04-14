from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import dearpygui.dearpygui as dpg

from ui._types import DpgTag

if TYPE_CHECKING:
    from ui.dpg_themes import DpgThemes
    from ui.page_manager import PageManager


class Page(ABC):
    """Abstract base class for a top-level application page.

    A Page owns a content container built once under a parent and a set of
    menus that are added to a menu bar on activation and removed on
    deactivation. Only one page in the application should be active at any
    given time; the PageManager enforces this.

    The shared :class:`DpgThemes` instance is owned by the MainWindow and
    passed in so that all pages render against the same underlying DPG
    theme handles.

    Subclasses must define:
        name             - unique string identifier used by PageManager.
        _build_ui()      - add content widgets; the child window container
                           is already created by the base class and is the
                           implicit DearPyGUI parent when _build_ui() runs.
        _install_menus() - create the page's menus under self._menu_bar
                           and append each created menu's tag to
                           self._menu_tags so the base class can remove
                           them automatically on deactivation.
    """

    name : str

    def __init__(
        self,
        parent: DpgTag,
        menu_bar: DpgTag,
        page_manager: PageManager,
        themes: DpgThemes,
    ) -> None:
        self._parent: DpgTag = parent
        self._menu_bar: DpgTag = menu_bar
        self._page_manager: PageManager = page_manager
        self._themes: DpgThemes = themes
        self._content_tag: DpgTag = dpg.generate_uuid()
        self._menu_tags: list[DpgTag] = []
        self._active: bool = False
        with dpg.child_window(tag=self._content_tag, parent=self._parent, border=False, show=False):
            self._build_ui()

    @abstractmethod
    def _build_ui(self) -> None:
        ...

    @abstractmethod
    def _install_menus(self) -> None:
        ...

    @property
    def is_active(self) -> bool:
        return self._active

    def activate(self) -> None:
        if self._active:
            return
        dpg.show_item(self._content_tag)
        self._install_menus()
        self._active = True
        self._on_activated()

    def _on_activated(self) -> None:
        """Hook called after the page becomes active. Override to set focus,
        refresh derived state, etc. Base implementation is a no-op."""
        pass

    def deactivate(self) -> None:
        if not self._active:
            return
        dpg.hide_item(self._content_tag)
        for tag in self._menu_tags:
            if dpg.does_item_exist(tag):
                dpg.delete_item(tag)
        self._menu_tags.clear()
        self._active = False

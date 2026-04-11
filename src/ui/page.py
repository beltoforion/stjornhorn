from abc import ABC, abstractmethod

import dearpygui.dearpygui as dpg


class Page(ABC):
    """Abstract base class for a top-level application page.

    A Page owns a content container built once under a parent and a set of
    menus that are added to a menu bar on activation and removed on
    deactivation. Only one page in the application should be active at any
    given time; the PageManager enforces this.

    Subclasses implement:
        _build_ui()      - create the page content (use self._content_tag
                           as the root container tag, self._parent as the
                           parent, and pass show=False so the page starts
                           hidden).
        _install_menus() - create the page's menus under self._menu_bar
                           and append each created menu's tag to
                           self._menu_tags so the base class can remove
                           them automatically on deactivation.
    """

    def __init__(self, parent: str, menu_bar: str) -> None:
        self._parent: str = parent
        self._menu_bar: str = menu_bar
        self._content_tag: int = dpg.generate_uuid()
        self._menu_tags: list[int | str] = []
        self._active: bool = False
        self._build_ui()

    @abstractmethod
    def _build_ui(self) -> None:
        ...

    @abstractmethod
    def _install_menus(self) -> None:
        ...

    @property
    def active(self) -> bool:
        return self._active

    def activate(self) -> None:
        if self._active:
            return
        dpg.show_item(self._content_tag)
        self._install_menus()
        self._active = True

    def deactivate(self) -> None:
        if not self._active:
            return
        dpg.hide_item(self._content_tag)
        for tag in self._menu_tags:
            if dpg.does_item_exist(tag):
                dpg.delete_item(tag)
        self._menu_tags.clear()
        self._active = False

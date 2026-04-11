from ui.page import Page


class PageManager:
    """Owns a set of named pages and guarantees that only one is active."""

    def __init__(self) -> None:
        self._pages: dict[str, Page] = {}
        self._active: Page | None = None

    def register(self, page: Page) -> None:
        if page.name in self._pages:
            raise ValueError(f"Page '{page.name}' is already registered")
        self._pages[page.name] = page

    def activate(self, name: str) -> None:
        if name not in self._pages:
            raise KeyError(f"Unknown page: '{name}'")

        target = self._pages[name]
        if self._active is target:
            return

        if self._active is not None:
            self._active.deactivate()

        target.activate()
        self._active = target

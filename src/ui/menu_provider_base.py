from abc import ABC, abstractmethod


class MenuProviderBase(ABC):
    @abstractmethod
    def add_menu(self, parent_tag : str) -> None:
        pass

from __future__ import annotations

from typing_extensions import override

from PySide6.QtWidgets import QComboBox, QGraphicsItem, QWidget


class SceneAwareComboBox(QComboBox):
    """QComboBox that keeps its popup above overlapping graphics items.

    When a QComboBox is embedded via QGraphicsProxyWidget, Qt renders its
    popup as a child proxy of the host proxy widget. Two Z-order issues
    arise while the popup is visible:

    * Sibling NodeItems at the same Z can occlude the popup (inter-node).
    * The popup extends below its host proxy, and sibling child items of
      the NodeItem with higher Z (e.g. the close button, ports) paint on
      top of it (intra-node).

    While the popup is open we boost the host NodeItem's Z above other
    nodes AND the params proxy's Z above its NodeItem siblings, then
    restore both on close.
    """

    _POPUP_Z_BOOST: float = 10_000.0

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._raised_proxy: QGraphicsItem | None = None
        self._raised_node: QGraphicsItem | None = None
        self._saved_proxy_z: float | None = None
        self._saved_node_z: float | None = None

    @override
    def showPopup(self) -> None:
        if self._raised_node is None:
            proxy = self.window().graphicsProxyWidget()
            if proxy is not None:
                node = proxy
                while node.parentItem() is not None:
                    node = node.parentItem()
                self._raised_node = node
                self._saved_node_z = node.zValue()
                node.setZValue(self._saved_node_z + self._POPUP_Z_BOOST)
                if proxy is not node:
                    self._raised_proxy = proxy
                    self._saved_proxy_z = proxy.zValue()
                    proxy.setZValue(self._saved_proxy_z + self._POPUP_Z_BOOST)
        super().showPopup()

    @override
    def hidePopup(self) -> None:
        super().hidePopup()
        if self._raised_proxy is not None and self._saved_proxy_z is not None:
            self._raised_proxy.setZValue(self._saved_proxy_z)
        if self._raised_node is not None and self._saved_node_z is not None:
            self._raised_node.setZValue(self._saved_node_z)
        self._raised_proxy = None
        self._raised_node = None
        self._saved_proxy_z = None
        self._saved_node_z = None

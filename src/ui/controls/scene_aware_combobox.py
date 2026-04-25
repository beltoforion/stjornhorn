from __future__ import annotations

from typing_extensions import override

from PySide6.QtGui import QColor, QPalette
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

    The popup container (a ``QComboBoxPrivateContainer`` QFrame) does not
    inherit ``autoFillBackground`` through the proxy on Windows, so the
    application stylesheet's dark colour never lands on a real fill —
    the dropdown ends up transparent over the scene canvas. We force the
    container opaque + paint its background ourselves the first time the
    popup is shown. (Issue: #136.)
    """

    _POPUP_Z_BOOST: float = 10_000.0

    _POPUP_BG_COLOR     = QColor(0x1f, 0x1f, 0x22)
    _POPUP_TEXT_COLOR   = QColor(0xe0, 0xe0, 0xe0)
    _POPUP_HIGHLIGHT    = QColor(0x3a, 0x5b, 0x8a)
    _POPUP_HIGHLIGHT_TX = QColor(0xff, 0xff, 0xff)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._raised_proxy: QGraphicsItem | None = None
        self._raised_node: QGraphicsItem | None = None
        self._saved_proxy_z: float | None = None
        self._saved_node_z: float | None = None
        self._popup_themed: bool = False

    def _theme_popup_once(self) -> None:
        """Force the popup container + view to render with a dark background.

        The fix has to be applied to the *container* (the view's parent
        QFrame), not just the view: when the combo is hosted in a graphics
        proxy, the container is the widget that ends up painting through to
        the scene as transparent.
        """
        if self._popup_themed:
            return
        view = self.view()
        container = view.parentWidget() if view is not None else None
        for w in (container, view):
            if w is None:
                continue
            w.setAutoFillBackground(True)
            pal = w.palette()
            pal.setColor(QPalette.Window,          self._POPUP_BG_COLOR)
            pal.setColor(QPalette.Base,            self._POPUP_BG_COLOR)
            pal.setColor(QPalette.Text,            self._POPUP_TEXT_COLOR)
            pal.setColor(QPalette.WindowText,      self._POPUP_TEXT_COLOR)
            pal.setColor(QPalette.Highlight,       self._POPUP_HIGHLIGHT)
            pal.setColor(QPalette.HighlightedText, self._POPUP_HIGHLIGHT_TX)
            w.setPalette(pal)
        self._popup_themed = True

    @override
    def showPopup(self) -> None:
        self._theme_popup_once()
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

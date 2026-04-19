from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class ErrorBanner(QFrame):
    """Floating error toast anchored to the top-right of a parent widget.

    Used to surface multi-line error messages that do not fit into the
    single-line status bar. The banner stays visible until the user clicks
    its close button; a subsequent :meth:`show_error` replaces the text in
    place. A parent-resize event filter keeps the banner glued to the
    upper-right corner of the client area.
    """

    MARGIN: int = 12
    MAX_WIDTH: int = 480
    MAX_HEIGHT_FRACTION: float = 0.6
    MIN_WIDTH: int = 240
    MIN_HEIGHT: int = 120
    OPACITY: float = 0.85

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)

        self.setObjectName("ErrorBanner")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # Let the red backdrop blend slightly with whatever is underneath
        # (canvas, docks) so the banner reads as an overlay rather than an
        # opaque panel.
        opacity = QGraphicsOpacityEffect(self)
        opacity.setOpacity(self.OPACITY)
        self.setGraphicsEffect(opacity)
        self.setStyleSheet(
            """
            QFrame#ErrorBanner {
                background: #5a1e22;
                border: 1px solid #e05050;
                border-radius: 4px;
            }
            QLabel#ErrorBannerTitle {
                color: #ffdcdc;
                font-weight: bold;
                background: transparent;
            }
            QLabel#ErrorBannerMessage {
                color: #ffeaea;
                background: transparent;
            }
            QToolButton#ErrorBannerClose {
                color: #ffdcdc;
                background: transparent;
                border: none;
                padding: 0 6px;
                font-size: 14px;
            }
            QToolButton#ErrorBannerClose:hover {
                color: #ffffff;
            }
            QScrollArea#ErrorBannerScroll {
                background: transparent;
                border: none;
            }
            QScrollArea#ErrorBannerScroll > QWidget > QWidget {
                background: transparent;
            }
            """
        )

        self._title = QLabel("Error")
        self._title.setObjectName("ErrorBannerTitle")

        self._close = QToolButton()
        self._close.setObjectName("ErrorBannerClose")
        self._close.setText("\u2715")
        self._close.setToolTip("Dismiss")
        self._close.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close.clicked.connect(self.hide)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        header.addWidget(self._title)
        header.addStretch(1)
        header.addWidget(self._close)

        self._message = QLabel("")
        self._message.setObjectName("ErrorBannerMessage")
        self._message.setWordWrap(True)
        self._message.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._message.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self._scroll = QScrollArea()
        self._scroll.setObjectName("ErrorBannerScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setWidget(self._message)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(6)
        layout.addLayout(header)
        layout.addWidget(self._scroll)

        parent.installEventFilter(self)
        self.hide()

    # ── Public API ─────────────────────────────────────────────────────────────

    def show_error(self, message: str, *, title: str = "Error") -> None:
        """Display ``message`` in the banner and bring it to the front."""
        
        self._title.setText(title)
        self._message.setText(message)
        self._reposition()
        self.show()
        self.raise_()

    # ── Parent resize tracking ─────────────────────────────────────────────────

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # type: ignore[override]
        if obj is self.parent() and event.type() == QEvent.Type.Resize and self.isVisible():
            self._reposition()
        return super().eventFilter(obj, event)

    def _reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        
        margin = self.MARGIN
        max_w = min(self.MAX_WIDTH, max(self.MIN_WIDTH, parent.width() - 2 * margin))
        max_h = max(self.MIN_HEIGHT, int(parent.height() * self.MAX_HEIGHT_FRACTION))
        self.setFixedWidth(max_w)
        self.setMaximumHeight(max_h)

        # adjustSize lets the banner shrink-to-fit short messages and keeps
        # the scroll area kicking in only when the message would exceed max_h.
        self.adjustSize()
        
        x = parent.width() - self.width() - margin
        y = margin
        self.move(max(margin, x), y)

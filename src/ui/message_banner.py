from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QGuiApplication
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


class MessageBanner(QFrame):
    """Floating notification toast anchored to the top-right of a parent widget.

    Used to surface multi-line messages that do not fit into the single-line
    status bar. The banner stays visible until the user clicks its close
    button; a subsequent :meth:`show_error` / :meth:`show_warning` replaces
    the text in place. A parent-resize event filter keeps the banner glued
    to the upper-right corner of the client area.

    Three severities are supported:
      - **error** (red) — call :meth:`show_error`. Used for run-aborting
        problems the user must see (connection rejections, exceptions).
      - **warning** (amber) — call :meth:`show_warning`. Used for
        non-fatal issues that should not interrupt the run (e.g. a
        single frame failing to render in the preview).
      - **info** (blue) — call :meth:`show_info`. Used for neutral
        status messages with no problem implied (a node reporting
        progress, a flow announcing a milestone).
    """

    MARGIN: int = 12
    MAX_WIDTH: int = 480
    MAX_HEIGHT_FRACTION: float = 0.6
    MIN_WIDTH: int = 240
    MIN_HEIGHT: int = 120
    OPACITY: float = 0.85

    # Per-severity palette. Each style is built from the same template so
    # adding a new state (tweaking the header buttons, separator, etc.)
    # only edits one place. The warning palette stays warm-amber so it
    # reads as "attention needed" without the "something is broken"
    # weight of red. Selectors target every QToolButton inside the banner
    # so the copy and close buttons share the same look without per-name
    # rules.
    _STYLE_TEMPLATE: str = """
        QFrame#MessageBanner {{
            background: {bg};
            border: 1px solid {border};
            border-radius: 4px;
        }}
        QLabel#MessageBannerTitle {{
            color: {title_fg};
            font-weight: bold;
            background: transparent;
        }}
        QLabel#MessageBannerMessage {{
            color: {message_fg};
            background: transparent;
        }}
        QFrame#MessageBanner QToolButton {{
            color: {title_fg};
            background: transparent;
            border: none;
            padding: 0 6px;
            font-size: 14px;
        }}
        QFrame#MessageBanner QToolButton:hover {{
            color: #ffffff;
        }}
        QFrame#MessageBannerSeparator {{
            color: {border};
            background: {border};
            max-width: 1px;
        }}
        QScrollArea#MessageBannerScroll {{
            background: transparent;
            border: none;
        }}
        QScrollArea#MessageBannerScroll > QWidget > QWidget {{
            background: transparent;
        }}
    """

    _ERROR_STYLE: str = _STYLE_TEMPLATE.format(
        bg="#5a1e22",
        border="#e05050",
        title_fg="#ffdcdc",
        message_fg="#ffeaea",
    )

    _WARNING_STYLE: str = _STYLE_TEMPLATE.format(
        bg="#5a4a1e",
        border="#e0b850",
        title_fg="#fff0c8",
        message_fg="#fff5d8",
    )

    _INFO_STYLE: str = _STYLE_TEMPLATE.format(
        bg="#1e3a5a",
        border="#5090e0",
        title_fg="#d8e8ff",
        message_fg="#e8f0ff",
    )

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)

        self.setObjectName("MessageBanner")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # Let the backdrop blend slightly with whatever is underneath
        # (canvas, docks) so the banner reads as an overlay rather than an
        # opaque panel.
        opacity = QGraphicsOpacityEffect(self)
        opacity.setOpacity(self.OPACITY)
        self.setGraphicsEffect(opacity)
        self.setStyleSheet(self._ERROR_STYLE)

        self._title = QLabel("Error")
        self._title.setObjectName("MessageBannerTitle")

        self._copy = QToolButton()
        self._copy.setObjectName("MessageBannerCopy")
        self._copy.setText("⧉")
        self._copy.setToolTip("Copy message to clipboard")
        self._copy.setCursor(Qt.CursorShape.PointingHandCursor)
        self._copy.clicked.connect(self._copy_to_clipboard)

        # Vertical hairline keeps a visual gap between Copy and Close so a
        # mis-aimed click on the copy button does not dismiss the banner.
        self._separator = QFrame()
        self._separator.setObjectName("MessageBannerSeparator")
        self._separator.setFrameShape(QFrame.Shape.VLine)
        self._separator.setFrameShadow(QFrame.Shadow.Plain)
        self._separator.setFixedWidth(1)

        self._close = QToolButton()
        self._close.setObjectName("MessageBannerClose")
        self._close.setText("✕")
        self._close.setToolTip("Dismiss")
        self._close.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close.clicked.connect(self.hide)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        header.addWidget(self._title)
        header.addStretch(1)
        header.addWidget(self._copy)
        header.addWidget(self._separator)
        header.addWidget(self._close)

        self._message = QLabel("")
        self._message.setObjectName("MessageBannerMessage")
        self._message.setWordWrap(True)
        self._message.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._message.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self._scroll = QScrollArea()
        self._scroll.setObjectName("MessageBannerScroll")
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
        """Display *message* in the red error palette."""
        self._show(message, title, self._ERROR_STYLE)

    def show_warning(self, message: str, *, title: str = "Warning") -> None:
        """Display *message* in the amber warning palette.

        Non-blocking — the banner just appears in the corner and the
        caller continues; the user dismisses with the close button.
        """
        self._show(message, title, self._WARNING_STYLE)

    def show_info(self, message: str, *, title: str = "Info") -> None:
        """Display *message* in the blue info palette.

        Non-blocking; intended for neutral status notifications with
        no problem implied.
        """
        self._show(message, title, self._INFO_STYLE)

    def _copy_to_clipboard(self) -> None:
        """Copy the current banner message text onto the system clipboard."""
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._message.text())

    def _show(self, message: str, title: str, style: str) -> None:
        # setStyleSheet on each show so the palette flips correctly
        # when the same banner alternates between an error and a
        # warning (last-call-wins). polish/unpolish forces Qt to
        # re-resolve the stylesheet against the new selectors.
        self.setStyleSheet(style)
        self.style().unpolish(self)
        self.style().polish(self)

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

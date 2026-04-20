from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, QTimer, Qt
from PySide6.QtGui import QColor, QConicalGradient, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ui.theme import STATUS_MUTED_COLOR


class SpinnerWidget(QWidget):
    """Small indeterminate spinner intended for status-bar use.

    Renders a rotating conical-gradient arc at a fixed size so it fits
    cleanly next to status-bar labels. The internal :class:`QTimer`
    only ticks while the widget is visible, so placing several
    spinners on the UI costs nothing while they are idle.

    Use :meth:`start` to show the spinner and begin animating, and
    :meth:`stop` to freeze + hide it.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        size: int = 14,
        interval_ms: int = 60,
        color: QColor | None = None,
    ) -> None:
        super().__init__(parent)
        self._size = size
        self._angle = 0
        # Status-bar spinner defaults to the muted status colour so it
        # sits quietly alongside the "Running…" label without shouting.
        self._color = QColor(color if color is not None else STATUS_MUTED_COLOR)

        self.setFixedSize(QSize(size, size))
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._advance)

        self.hide()

    # ── Public API ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        self.show()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    # ── Qt overrides ───────────────────────────────────────────────────────────

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        # A 2 px pen reads clearly at 14 px without dominating the box.
        # The -1 inset keeps the stroke fully inside the widget rect so
        # anti-aliasing doesn't clip against the status bar background.
        pen_width = 2
        inset = pen_width / 2 + 0.5
        rect = QRectF(inset, inset, self._size - 2 * inset, self._size - 2 * inset)

        # A conical gradient from transparent → solid produces the
        # comet-tail fade that readers expect from a spinner; rotating
        # the gradient start each tick animates it.
        grad = QConicalGradient(rect.center(), -self._angle)
        transparent = QColor(self._color)
        transparent.setAlpha(0)
        grad.setColorAt(0.0, self._color)
        grad.setColorAt(1.0, transparent)

        pen = QPen(grad, pen_width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(pen)
        painter.drawArc(rect, 0, 360 * 16)
        painter.end()

    def _advance(self) -> None:
        self._angle = (self._angle + 30) % 360
        self.update()

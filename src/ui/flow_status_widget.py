from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from constants import APP_DISPLAY_NAME, APP_VERSION
from ui.spinner import SpinnerWidget


_RUNNING_SPINNER_SIZE = 28


class FlowStatusWidget(QWidget):
    """Toolbar status widget for the node editor.

    Has two modes selected via :class:`QStackedLayout`:

    * **Idle** — a single ``AppName vX.Y.Z`` label, visually identical
      to the default :class:`ui.app_version_status_widget.AppVersionStatusWidget`
      so the toolbar looks the same whether the editor is open or not.
    * **Running** — a spinner on the right; on the left, two stacked
      labels: the flow name in bold on top, the currently-executing
      node name muted beneath.

    The page drives the widget via :meth:`show_idle`, :meth:`show_running`
    and :meth:`set_current_node`. The widget owns no timers besides its
    spinner, so leaving it mounted while idle costs effectively nothing.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._stack = QStackedLayout(self)
        self._stack.setContentsMargins(0, 0, 0, 0)
        self._stack.setSpacing(0)

        # ── Idle page ──────────────────────────────────────────────────
        self._idle_page = QWidget()
        idle_layout = QHBoxLayout(self._idle_page)
        idle_layout.setContentsMargins(8, 0, 8, 0)
        idle_layout.setSpacing(0)

        idle_column = QVBoxLayout()
        idle_column.setContentsMargins(0, 0, 0, 0)
        idle_column.setSpacing(0)
        idle_column.addStretch(1)

        self._idle_name_label = QLabel(APP_DISPLAY_NAME)
        self._idle_name_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._idle_name_label.setStyleSheet("font-size: 14pt;")

        self._idle_version_label = QLabel(f"v{APP_VERSION}")
        self._idle_version_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._idle_version_label.setProperty("muted", True)

        idle_column.addWidget(self._idle_name_label)
        idle_column.addWidget(self._idle_version_label)
        idle_column.addStretch(1)
        idle_layout.addLayout(idle_column)
        self._stack.addWidget(self._idle_page)

        # ── Running page ───────────────────────────────────────────────
        self._running_page = QWidget()
        running_layout = QHBoxLayout(self._running_page)
        running_layout.setContentsMargins(8, 0, 8, 0)
        running_layout.setSpacing(10)

        labels_col = QVBoxLayout()
        labels_col.setContentsMargins(0, 0, 0, 0)
        labels_col.setSpacing(0)
        # Stretches above and below centre the pair within the widget's
        # full height so the labels line up with the toolbar action row
        # rather than hugging the top edge.
        labels_col.addStretch(1)

        self._flow_label = QLabel("")
        self._flow_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        # Bold + larger size for the flow name so it reads as the
        # primary label. Inline stylesheet keeps the theme's palette
        # colour; setProperty-based selectors would need a QSS rule we
        # don't otherwise need.
        self._flow_label.setStyleSheet("font-size: 14pt; font-weight: bold;")

        self._node_label = QLabel("")
        self._node_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._node_label.setProperty("muted", True)

        labels_col.addWidget(self._flow_label)
        labels_col.addWidget(self._node_label)
        labels_col.addStretch(1)

        self._spinner = SpinnerWidget(size=_RUNNING_SPINNER_SIZE, interval_ms=60)

        running_layout.addLayout(labels_col, 1)
        running_layout.addWidget(self._spinner, 0, Qt.AlignmentFlag.AlignVCenter)
        self._stack.addWidget(self._running_page)

        self._stack.setCurrentWidget(self._idle_page)

    # ── Public API ─────────────────────────────────────────────────────────────

    def show_idle(self) -> None:
        """Switch back to the app-name/version display and stop the spinner."""
        self._spinner.stop()
        self._flow_label.clear()
        self._node_label.clear()
        self._stack.setCurrentWidget(self._idle_page)

    def show_running(self, flow_name: str) -> None:
        """Switch to running mode; ``flow_name`` is shown in bold.

        The node label starts blank — call :meth:`set_current_node` as
        soon as the first node starts processing to populate it.
        """
        self._flow_label.setText(flow_name)
        self._node_label.setText("")
        self._stack.setCurrentWidget(self._running_page)
        self._spinner.start()

    def set_current_node(self, display_name: str) -> None:
        """Update the muted "current node" label shown under the flow name."""
        self._node_label.setText(display_name)

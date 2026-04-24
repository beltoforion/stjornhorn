from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from ui.app_version_status_widget import AppVersionStatusWidget
from ui.spinner import SpinnerWidget
from ui.theme import STATUS_WARN_COLOR


_RUNNING_SPINNER_SIZE = 28


class FlowStatusWidget(QWidget):
    """Toolbar status widget for the node editor.

    Has two modes selected via :class:`QStackedLayout`:

    * **Idle** — the default :class:`AppVersionStatusWidget` (app name,
      version and Python runtime), with an amber "● Unsaved changes" row
      that appears only when the editor has uncommitted edits. So the
      toolbar looks the same as other pages while the flow is clean,
      and surfaces unsaved state the moment it arises.
    * **Running** — a spinner on the right; on the left, two stacked
      labels: the flow name in bold on top, the currently-executing
      node name muted beneath.

    The page drives the widget via :meth:`show_idle`, :meth:`show_running`,
    :meth:`set_current_node` and :meth:`set_unsaved`. The widget owns no
    timers besides its spinner, so leaving it mounted while idle costs
    effectively nothing.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._stack = QStackedLayout(self)
        self._stack.setContentsMargins(0, 0, 0, 0)
        self._stack.setSpacing(0)

        # ── Idle page ──────────────────────────────────────────────────
        # Reuse AppVersionStatusWidget so the idle view is pixel-identical
        # to every other page's default status widget; the unsaved row is
        # tacked on below it and hidden until the editor marks dirty.
        self._idle_page = QWidget()
        idle_layout = QHBoxLayout(self._idle_page)
        idle_layout.setContentsMargins(0, 0, 0, 0)
        idle_layout.setSpacing(0)

        idle_column = QVBoxLayout()
        idle_column.setContentsMargins(0, 0, 0, 0)
        idle_column.setSpacing(0)

        self._app_version_widget = AppVersionStatusWidget()
        idle_column.addWidget(self._app_version_widget)

        self._unsaved_label = QLabel("● Unsaved changes")
        self._unsaved_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._unsaved_label.setContentsMargins(8, 0, 8, 4)
        self._unsaved_label.setStyleSheet(
            f"color: {STATUS_WARN_COLOR.name()};"
        )
        self._unsaved_label.hide()
        idle_column.addWidget(self._unsaved_label)

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
        """Switch back to the app-name/version display and stop the spinner.

        The unsaved-changes row stays in whatever state
        :meth:`set_unsaved` last put it — leaving a run doesn't clean
        the flow.
        """
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

    def set_unsaved(self, unsaved: bool) -> None:
        """Show or hide the amber "● Unsaved changes" row in idle mode."""
        self._unsaved_label.setVisible(unsaved)

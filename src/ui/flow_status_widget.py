from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from ui.app_version_status_widget import AppVersionStatusWidget
from ui.icons import material_icon
from ui.spinner import SpinnerWidget
from ui.theme import STATUS_WARN_COLOR


_RUNNING_SPINNER_SIZE = 28
_UNSAVED_ICON_SIZE = 24


class FlowStatusWidget(QWidget):
    """Toolbar status widget for the node editor.

    Has two modes selected via :class:`QStackedLayout`:

    * **Idle** — on the right, the default :class:`AppVersionStatusWidget`
      (app name, version and Python runtime); on the left, a left-aligned
      amber warning icon with "Unsaved changes" underneath, shown only
      when the editor has uncommitted edits. So the toolbar looks the
      same as other pages while the flow is clean, and surfaces unsaved
      state the moment it arises.
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
        # Two columns: a left-aligned unsaved-changes affordance (hidden
        # until the editor marks dirty), and the standard right-aligned
        # AppVersionStatusWidget that every page shows. Reusing the
        # widget keeps the idle view pixel-identical to other pages.
        self._idle_page = QWidget()
        idle_layout = QHBoxLayout(self._idle_page)
        idle_layout.setContentsMargins(8, 0, 0, 0)
        idle_layout.setSpacing(0)

        self._unsaved_widget = self._build_unsaved_widget()
        self._unsaved_widget.hide()
        idle_layout.addWidget(
            self._unsaved_widget, 0, Qt.AlignmentFlag.AlignVCenter
        )
        idle_layout.addStretch(1)
        idle_layout.addWidget(AppVersionStatusWidget())

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

        The unsaved-changes affordance stays in whatever state
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
        """Show or hide the left-aligned unsaved-changes icon + caption."""
        self._unsaved_widget.setVisible(unsaved)

    # ── Internals ──────────────────────────────────────────────────────────────

    def _build_unsaved_widget(self) -> QWidget:
        """Build the icon-over-caption "Unsaved changes" affordance.

        Standalone helper so __init__ reads as layout wiring rather
        than pixel math. Centres a 24 px amber warning glyph over a
        muted amber caption; the column is centred inside whichever
        height the toolbar hands us.
        """
        container = QWidget()
        column = QVBoxLayout(container)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(2)

        icon = QLabel()
        icon.setPixmap(
            material_icon("warning", color=STATUS_WARN_COLOR).pixmap(
                QSize(_UNSAVED_ICON_SIZE, _UNSAVED_ICON_SIZE)
            )
        )
        icon.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)

        caption = QLabel("Unsaved changes")
        caption.setAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
        )
        caption.setStyleSheet(
            f"color: {STATUS_WARN_COLOR.name()}; font-size: 9pt;"
        )

        column.addWidget(icon)
        column.addWidget(caption)
        return container

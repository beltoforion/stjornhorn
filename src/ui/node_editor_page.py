from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QStatusBar,
    QVBoxLayout,
)

from constants import FLOW_DIR
from core.flow import Flow, is_valid_flow_name
from core.io_data import IMAGE_TYPES
from core.node_base import SinkNodeBase, SourceNodeBase
from ui.flow_io import FlowIoError, load_flow_into, save_flow_to
from ui.flow_scene import FlowScene
from ui.flow_view import FlowView
from ui.icons import material_icon
from typing_extensions import override

from ui.page import PageBase, ToolbarSection
from ui.node_list import NodeList
from ui.recent_flows import RecentFlowsManager
from ui.error_banner import ErrorBanner
from ui.theme import STATUS_MUTED_COLOR, STATUS_OK_COLOR
from ui.viewer_panel import ViewerPanel

if TYPE_CHECKING:
    from core.node_registry import NodeRegistry

logger = logging.getLogger(__name__)

_FLOW_FILE_EXTENSION = ".flowjs"
_FLOW_FILE_FILTER    = "Flow (*.flowjs);;All files (*)"


class NodeEditorPage(PageBase):
    """The editor. Central canvas + palette dock (left) + Output Inspector (left).

    Dockable panels are hosted on an inner QMainWindow so the palette and
    Output Inspector can be dragged around, floated, or closed by the user.
    By default the Node List and Output Inspector share the left dock area
    with an equal 50/50 vertical split. Toolbar actions are exposed via
    :meth:`page_toolbar_actions` so MainWindow can render them in the
    global toolbar next to the page-selector radio group.

    Signal :attr:`title_changed` fires up to MainWindow whenever the active
    flow name changes.
    """

    def __init__(
        self,
        registry: NodeRegistry,
        recent_flows: RecentFlowsManager | None = None,
    ) -> None:
        super().__init__()
        self._registry = registry
        self._recent_flows = recent_flows
        self._flow: Flow | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Inner QMainWindow hosting the canvas + docks ──
        self._inner = QMainWindow()
        self._inner.setDockOptions(
            QMainWindow.DockOption.AllowTabbedDocks | QMainWindow.DockOption.AllowNestedDocks
        )
        outer.addWidget(self._inner)

        # Canvas.
        self._scene = FlowScene()
        self._view  = FlowView(self._scene)
        self._inner.setCentralWidget(self._view)

        # Node list dock (left, formerly "Palette").
        self._node_list = NodeList(registry)
        self._node_list_dock = QDockWidget("Node List", self._inner)
        self._node_list_dock.setObjectName("NodeListDock")
        self._node_list_dock.setWidget(self._node_list)
        self._node_list_dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        self._inner.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._node_list_dock)

        # Output Inspector dock — also on the left, stacked under the Node
        # List with a 50/50 vertical split applied after the widget is shown.
        self._viewer = ViewerPanel()
        self._viewer_dock = QDockWidget("Output Inspector", self._inner)
        self._viewer_dock.setObjectName("OutputInspectorDock")
        self._viewer_dock.setWidget(self._viewer)
        self._viewer_dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        self._inner.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._viewer_dock)
        self._inner.splitDockWidget(
            self._node_list_dock, self._viewer_dock, Qt.Orientation.Vertical,
        )
        self._initial_split_applied = False

        # Actions: reused by both the page menu and the main toolbar.
        self._actions = self._build_actions()

        # Status bar at the bottom of the inner window.
        self._status_bar = QStatusBar(self._inner)
        self._status_label = QLabel("")
        self._status_bar.addWidget(self._status_label, 1)
        self._inner.setStatusBar(self._status_bar)

        # Floating error banner anchored to the top-right of the page's
        # client area. Used instead of the status bar for failures because
        # error messages can be long and multi-line.
        self._error_banner = ErrorBanner(self._inner)

        # Wire scene → viewer.
        self._scene.selected_node_changed.connect(self._viewer.show_node)
        # Surface interactive-connection errors (type mismatches) in the
        # error banner instead of swallowing them inside FlowScene.
        self._scene.connection_error.connect(self._on_connection_error)

        # Debounce timer for reactive (auto-run) flows.  A 300 ms single-shot
        # timer is restarted on every param change; it fires _on_run_clicked
        # only after the user pauses editing.
        self._live_timer = QTimer(self)
        self._live_timer.setSingleShot(True)
        self._live_timer.setInterval(300)
        self._live_timer.timeout.connect(self._on_run_clicked)
        self._scene.param_changed.connect(self._on_param_changed)

    # ── Page hooks ─────────────────────────────────────────────────────────────

    def page_title(self) -> str:
        # Return just the flow name (or empty) so MainWindow renders a
        # title like "Sparklehoof — MyFlow" rather than embedding the
        # page's role in the window caption.
        if self._flow is not None:
            return self._flow.name
        return ""

    @override
    def page_selector_label(self) -> str:
        return "Editor"

    @override
    def page_selector_icon(self) -> QIcon:
        return material_icon("account_tree")

    def page_toolbar_sections(self) -> list[ToolbarSection]:
        return [
            ToolbarSection("Flow", [
                self._actions["run"],
                self._actions["save"],
                self._actions["save_as"],
                self._actions["open"],
                self._actions["clear"],
            ]),
            ToolbarSection("View", [
                self._actions["fit"],
                self._actions["reset_zoom"],
                self._actions["stack_vertical"],
            ]),
        ]

    def page_menus(self) -> list[QMenu]:
        # Single "Node Editor" menu mirroring the toolbar actions plus
        # a View submenu to toggle the docks. The menu itself is rebuilt
        # on every activation because QMenu cannot be easily re-parented
        # across hosts.
        menu = QMenu("Node Editor")
        menu.addAction(self._actions["run"])
        menu.addAction(self._actions["save"])
        menu.addAction(self._actions["save_as"])
        menu.addAction(self._actions["open"])
        menu.addSeparator()
        menu.addAction(self._actions["clear"])
        menu.addSeparator()

        view_menu = menu.addMenu("View")
        view_menu.addAction(self._node_list_dock.toggleViewAction())
        view_menu.addAction(self._viewer_dock.toggleViewAction())
        return [menu]

    def on_activated(self) -> None:
        # Refresh menu label via title_changed so MainWindow picks up the
        # current flow name. Also refresh the viewer to whatever is
        # currently selected (nothing, typically).
        self.title_changed.emit(self.page_title())
        self._viewer.refresh()

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        # Qt only honours resizeDocks after the main window has real geometry,
        # so defer the 50/50 split until the first show.
        if not self._initial_split_applied:
            self._initial_split_applied = True
            QTimer.singleShot(0, self._equalize_left_docks)

    def _equalize_left_docks(self) -> None:
        """Give the Node List and Output Inspector equal height in the left area."""
        h = max(self._inner.height(), 2)
        half = h // 2
        self._inner.resizeDocks(
            [self._node_list_dock, self._viewer_dock],
            [half, h - half],
            Qt.Orientation.Vertical,
        )

    # ── Public API (called by MainWindow) ──────────────────────────────────────

    def set_flow(self, flow: Flow) -> None:
        """Replace the editor's current flow with a fresh empty one."""
        self._flow = flow
        self._scene.set_flow(flow)
        self._viewer.show_node(None)
        self._set_status("", kind="muted")
        self.title_changed.emit(self.page_title())

    def load_flow(self, path: Path) -> bool:
        """Load a flow from disk. Returns True on success, False on failure
        (status line shows the reason)."""
        try:
            flow = load_flow_into(path, self._scene)
        except FlowIoError as err:
            logger.warning("Failed to load flow from %s: %s", path, err)
            self._set_status(f"Open failed ({err})", kind="fail")
            return False
        self._flow = flow
        self._viewer.show_node(None)
        self.title_changed.emit(self.page_title())
        # Fit the freshly-loaded graph into the view. Deferred so it runs
        # after pending layout events settle — viewport geometry isn't
        # final yet when load_flow runs during the first paint.
        QTimer.singleShot(0, self._view.fit_to_contents)
        self._set_status(
            f"Loaded {_display_path(path)} at {datetime.now().strftime('%H:%M:%S')}",
            kind="ok",
        )
        if self._recent_flows is not None:
            self._recent_flows.add(path)
        return True

    # ── Actions ────────────────────────────────────────────────────────────────

    def _build_actions(self) -> dict[str, QAction]:
        def mk(text: str, icon_name: str, slot) -> QAction:
            a = QAction(material_icon(icon_name), text, self)
            a.triggered.connect(slot)
            return a

        return {
            "run":     mk("Run",      "play_arrow",  self._on_run_clicked),
            "save":    mk("Save",     "save",        self._on_save_clicked),
            "save_as": mk("Save As…", "save_as",     self._on_save_as_clicked),
            "open":    mk("Open",     "folder_open", self._on_open_clicked),
            "clear":   mk("Clear",    "delete",      self._on_clear_clicked),
            "fit":     mk("Fit",      "zoom_out_map",    self._view.fit_to_contents),
            "reset_zoom": mk("1:1", "fullscreen_exit", self._view.reset_zoom),
            "stack_vertical": mk(
                "Stack Vertically", "view_stream", self._on_stack_vertical_clicked,
            ),
        }

    # ── Action handlers ────────────────────────────────────────────────────────

    def _on_stack_vertical_clicked(self) -> None:
        """Align selected nodes on a shared X axis and stack them vertically."""
        moved = self._scene.stack_selected_vertically()
        if moved == 0:
            self._set_status(
                "Select two or more nodes to stack them vertically.",
                kind="muted",
            )

    def _on_run_clicked(self) -> None:
        if self._flow is None:
            self._set_status("No flow to run", kind="fail")
            return
        try:
            self._flow.run()
        except Exception as err:
            logger.exception("Flow run failed")
            detail = str(err).strip() or "(no message)"
            self._set_status(f"Run failed ({type(err).__name__}): {detail}", kind="fail")
            return
        self._set_status(
            f"Ran at {datetime.now().strftime('%H:%M:%S')}",
            kind="ok",
        )
        if self._viewer.current_node is None:
            # Nothing selected yet — auto-show the most downstream node
            # that produced image data so the user sees a result immediately.
            best = self._best_viewer_node()
            if best is not None:
                self._viewer.show_node(best)
        else:
            self._viewer.refresh()

    def _best_viewer_node(self):
        """Return the most downstream non-sink node with IMAGE output data.

        Iterates the flow's nodes in reverse registration order (later-added
        nodes tend to be further downstream) and returns the first one that
        has at least one IMAGE output port with data after a run.  Returns
        ``None`` when the flow has no such node.
        """
        if self._flow is None:
            return None
        for node in reversed(self._flow.nodes):
            if isinstance(node, SinkNodeBase):
                continue
            for port in node.outputs:
                if (port.emits & IMAGE_TYPES) and port.last_emitted is not None:
                    return node
        return None

    def _on_param_changed(self) -> None:
        """Restart the debounce timer whenever any node parameter changes.

        The timer fires :meth:`_on_run_clicked` after 300 ms of inactivity,
        but only when the flow contains at least one reactive source (i.e. a
        still-image source).  Video and other non-reactive sources are not
        auto-run so that editing their parameters does not restart a lengthy
        decode on every keystroke.
        """
        if self._flow is not None and self._has_reactive_source():
            self._live_timer.start()

    def _has_reactive_source(self) -> bool:
        """Return True if the flow has at least one reactive source node."""
        if self._flow is None:
            return False
        return any(
            isinstance(n, SourceNodeBase) and n.is_reactive
            for n in self._flow.nodes
        )

    def _on_save_clicked(self) -> None:
        if self._flow is None:
            self._set_status("No flow to save", kind="fail")
            return
        path = FLOW_DIR / f"{self._flow.name}{_FLOW_FILE_EXTENSION}"
        try:
            save_flow_to(path, self._scene, self._flow)
        except OSError as err:
            logger.exception("Failed to save flow '%s'", self._flow.name)
            detail = err.strerror or str(err) or err.__class__.__name__
            self._set_status(f"Save failed: {detail}", kind="fail")
            return
        self._set_status(
            f"Saved to {_display_path(path)} at {datetime.now().strftime('%H:%M:%S')}",
            kind="ok",
        )
        if self._recent_flows is not None:
            self._recent_flows.add(path)

    def _on_save_as_clicked(self) -> None:
        if self._flow is None:
            self._set_status("No flow to save", kind="fail")
            return
        FLOW_DIR.mkdir(parents=True, exist_ok=True)
        suggested = str(FLOW_DIR / f"{self._flow.name}{_FLOW_FILE_EXTENSION}")
        path_str, _ = QFileDialog.getSaveFileName(
            self, "Save Flow As", suggested, _FLOW_FILE_FILTER,
        )
        if not path_str:
            return
        path = Path(path_str)
        # Flow names are restricted to a filesystem-safe charset; reject
        # stems that would otherwise be silently mangled by
        # sanitize_flow_name, rather than save under a different name.
        new_name = path.stem
        if not is_valid_flow_name(new_name):
            self._set_status(
                f"Invalid flow name '{new_name}': use letters, digits, _ # + -",
                kind="fail",
            )
            return
        try:
            save_flow_to(path, self._scene, self._flow)
        except OSError as err:
            logger.exception("Failed to save flow to '%s'", path)
            detail = err.strerror or str(err) or err.__class__.__name__
            self._set_status(f"Save failed: {detail}", kind="fail")
            return
        self._flow.name = new_name
        self.title_changed.emit(self.page_title())
        self._set_status(
            f"Saved to {_display_path(path)} at {datetime.now().strftime('%H:%M:%S')}",
            kind="ok",
        )
        if self._recent_flows is not None:
            self._recent_flows.add(path)

    def _on_open_clicked(self) -> None:
        FLOW_DIR.mkdir(parents=True, exist_ok=True)
        path_str, _ = QFileDialog.getOpenFileName(
            self, "Open Flow", str(FLOW_DIR), _FLOW_FILE_FILTER,
        )
        if path_str:
            self.load_flow(Path(path_str))

    def _on_clear_clicked(self) -> None:
        if self._flow is None:
            return
        if self._scene.iter_node_items() and QMessageBox.question(
            self, "Clear all?",
            "Remove every node and connection from this flow?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        # Start from a fresh Flow with the same name so Save still targets
        # the same file. The scene clears via set_flow.
        self.set_flow(Flow(name=self._flow.name))

    # ── Scene error handlers ───────────────────────────────────────────────────

    def _on_connection_error(self, message: str) -> None:
        """Surface a FlowScene connection rejection in the error banner."""
        self._set_status(message, kind="fail")

    # ── Status line ────────────────────────────────────────────────────────────

    def _set_status(self, message: str, *, kind: str) -> None:
        # Failures go to the floating error banner so long / multi-line
        # messages are readable. The status bar keeps the last success or
        # informational message so the user can still glance at it.
        if kind == "fail":
            self._error_banner.show_error(message)
            return
        color = {
            "ok":    STATUS_OK_COLOR,
            "muted": STATUS_MUTED_COLOR,
        }.get(kind, STATUS_MUTED_COLOR)
        self._status_label.setText(message)
        self._status_label.setToolTip(message)
        self._status_label.setStyleSheet(
            f"color: rgb({color.red()},{color.green()},{color.blue()});"
        )
        # A successful action implicitly clears any stale error.
        if kind == "ok":
            self._error_banner.hide()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _display_path(path: Path) -> str:
    """Return ``path`` relative to cwd when possible, otherwise absolute.

    Resolves symlinks on both sides so a path that differs from cwd only
    via a symlink (e.g. ``~/Desktop/repo`` → ``~/Code/repo``) is still
    shown in the shorter relative form.
    """
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except (OSError, ValueError):
        return str(path)

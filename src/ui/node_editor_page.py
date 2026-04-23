from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QThread, QTimer
from PySide6.QtGui import QAction, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from constants import FLOW_DIR
from core.flow import Flow, is_valid_flow_name
from core.flow_runner import FlowRunner
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
from ui.flow_status_widget import FlowStatusWidget
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
    flow name changes. The toolbar's right-aligned status slot is owned by
    this page via :class:`FlowStatusWidget` — it shows the app/version by
    default and flips to a spinner + flow/node labels while a run is in
    flight.
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

        # Worker thread used by _on_run_clicked. Lazily created on the first
        # run and reused; cleaned up when the run finishes. While a run is in
        # flight, _run_thread is not None — this doubles as the "busy" flag
        # that suppresses re-entrant Run clicks and reactive auto-runs.
        self._run_thread: QThread | None = None
        self._run_runner: FlowRunner | None = None

        # Right-aligned toolbar status widget. Shows the app name + version
        # while idle; swaps to a flow-running view during executions.
        self._flow_status_widget = FlowStatusWidget()

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
        # A floating QDockWidget defaults to a Qt.Tool window, which on most
        # desktop environments lacks maximise / fullscreen affordances.
        # Promote it to a regular top-level window when it floats so the
        # user can inspect large outputs in full screen; F11 toggles
        # fullscreen while the dock is detached.
        self._viewer_dock.topLevelChanged.connect(self._on_viewer_top_level_changed)
        self._viewer_fullscreen_shortcut = QShortcut(
            QKeySequence(Qt.Key.Key_F11), self._viewer_dock
        )
        self._viewer_fullscreen_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._viewer_fullscreen_shortcut.activated.connect(
            self._toggle_viewer_fullscreen
        )

        # Actions: reused by both the page menu and the main toolbar.
        self._actions = self._build_actions()
        # Stack actions need at least two selected nodes; keep them disabled
        # until that is true and toggle them on selection changes.
        self._actions["stack_vertical"].setEnabled(False)
        self._actions["stack_horizontal"].setEnabled(False)
        self._scene.selectionChanged.connect(self._update_selection_actions)

        # Status bar at the bottom of the inner window. The running-flow
        # indicator lives on the main toolbar via FlowStatusWidget; the
        # status bar is kept purely for timestamp/ok messages.
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

        self.set_flow(Flow())  # start with an empty flow so the user can jump right in

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
                self._actions["stack_horizontal"],
            ]),
        ]

    @override
    def page_status_widget(self) -> QWidget | None:
        # The FlowStatusWidget manages its own idle/running transitions
        # internally, so MainWindow never needs to swap widgets on this
        # page — we hand back the same instance every call.
        return self._flow_status_widget

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

        if self._flow is not None:        
            logger.info(f"Setting active flow to: {flow.name}")
        else:
            logger.info("Setting active flow to: <None>")

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
            logger.warning(f"Failed to load flow from {path}: {err}")
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
            # Log every toolbar/menu activation before the real handler
            # runs. QAction.triggered passes a `checked` bool, which the
            # lambda swallows via *_.
            a.triggered.connect(
                lambda *_ , _text=text: logger.info("Toolbar action: %s", _text)
            )
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
                "V-Stack", "view_stream", self._on_stack_vertical_clicked,
            ),
            "stack_horizontal": mk(
                "H-Stack", "view_column", self._on_stack_horizontal_clicked,
            ),
        }

    # ── Action handlers ────────────────────────────────────────────────────────

    def _update_selection_actions(self) -> None:
        """Enable/disable selection-dependent actions based on node count."""
        from ui.node_item import NodeItem
        selected_nodes = sum(
            1 for s in self._scene.selectedItems() if isinstance(s, NodeItem)
        )
        self._actions["stack_vertical"].setEnabled(selected_nodes >= 2)
        self._actions["stack_horizontal"].setEnabled(selected_nodes >= 2)

    def _on_stack_vertical_clicked(self) -> None:
        """Align selected nodes on a shared X axis and stack them vertically."""
        self._scene.stack_selected_vertically()

    def _on_stack_horizontal_clicked(self) -> None:
        """Align selected nodes on a shared Y axis and stack them horizontally."""
        self._scene.stack_selected_horizontally()

    def _on_viewer_top_level_changed(self, floating: bool) -> None:
        """Promote the floating Output Inspector to a real top-level window.

        QDockWidget's default floating style is Qt.Tool, which most window
        managers render without maximise / fullscreen controls. Re-flag the
        window so the OS chrome offers those affordances, then re-show it
        (Qt hides a widget whenever its window flags change).
        """
        if not floating:
            return
        self._viewer_dock.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self._viewer_dock.show()

    def _toggle_viewer_fullscreen(self) -> None:
        """F11 handler: toggle fullscreen on the floating Output Inspector."""
        if not self._viewer_dock.isFloating():
            return
        if self._viewer_dock.isFullScreen():
            self._viewer_dock.showNormal()
        else:
            self._viewer_dock.showFullScreen()

    def _on_run_clicked(self) -> None:
        if self._flow is None:
            self._set_status("No flow to run", kind="fail")
            return
        if self._run_thread is not None:
            # A run is already in flight — ignore the click rather than
            # stacking runs on top of each other. The reactive debounce
            # timer can also land here if the user tweaks a param mid-run.
            return

        # Stop the reactive debounce timer while we run: if a param
        # change fires the timer during the run, _on_run_clicked will
        # early-return anyway, but stopping it keeps the intent obvious.
        self._live_timer.stop()
        self._set_toolbar_enabled(False)
        self._set_param_widgets_enabled(False)
        self._flow_status_widget.show_running(self._flow.name)
        self._set_status("Running…", kind="muted")

        thread = QThread(self)
        runner = FlowRunner(self._flow)
        runner.moveToThread(thread)

        thread.started.connect(runner.run)
        runner.finished.connect(self._on_run_finished)
        runner.failed.connect(self._on_run_failed)
        # Queued cross-thread signal — the worker fires node_started on
        # its own thread, Qt marshals it onto the UI thread slot.
        runner.node_started.connect(self._flow_status_widget.set_current_node)
        # Connection order matters: Qt invokes slots in the order they were
        # connected. We want deleteLater to post on the worker's event loop
        # *before* quit stops that same loop, so the runner is actually
        # destroyed. thread.deleteLater can then run on the UI thread after
        # the worker has terminated.
        runner.finished.connect(runner.deleteLater)
        runner.failed.connect(runner.deleteLater)
        runner.finished.connect(thread.quit)
        runner.failed.connect(lambda _msg: thread.quit())
        thread.finished.connect(thread.deleteLater)

        self._run_thread = thread
        self._run_runner = runner
        thread.start()

    def _on_run_finished(self) -> None:
        # Sinks may have just written output files; let every node's
        # param widgets re-evaluate filesystem-dependent state (e.g.
        # the FilePathParamWidget "view" button).
        for item in self._scene.iter_node_items():
            item.refresh_param_widgets()

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

        self._finalize_run()

    def _on_run_failed(self, detail: str) -> None:
        self._set_status(f"Run failed ({detail})", kind="fail")
        self._finalize_run()

    def _finalize_run(self) -> None:
        """Drop references to the worker thread and re-enable the Run action.

        Called from both terminal slots. The QThread itself is torn down
        via the ``thread.finished`` → ``deleteLater`` connections set up
        in :meth:`_on_run_clicked`; this just clears our handles so the
        next click starts a fresh thread.
        """
        self._run_thread = None
        self._run_runner = None
        self._set_toolbar_enabled(True)
        self._set_param_widgets_enabled(True)
        self._flow_status_widget.show_idle()

    def _set_param_widgets_enabled(self, enabled: bool) -> None:
        """Freeze or thaw every node's param editors for the duration of a run."""
        for item in self._scene.iter_node_items():
            item.set_params_enabled(enabled)

    def _set_toolbar_enabled(self, enabled: bool) -> None:
        """Disable every toolbar action for the duration of a run.

        Covers everything exposed via :meth:`page_toolbar_sections` — Run,
        the file actions and the view actions — so the user can't save,
        open or clear a flow that is still executing on the worker thread.
        When re-enabling, ``_update_selection_actions`` re-applies the
        selection-dependent gating for the stack actions instead of
        leaving them unconditionally enabled.
        """
        for action in self._actions.values():
            action.setEnabled(enabled)
        if enabled:
            self._update_selection_actions()

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
        old_name = self._flow.name
        self._flow.name = new_name
        try:
            save_flow_to(path, self._scene, self._flow)
        except OSError as err:
            self._flow.name = old_name
            logger.exception("Failed to save flow to '%s'", path)
            detail = err.strerror or str(err) or err.__class__.__name__
            self._set_status(f"Save failed: {detail}", kind="fail")
            return
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

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QThread, QTimer, Signal, Slot
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
    QWidget,
)

from constants import FLOW_DIR
from core import notifications
from core.flow import Flow, is_valid_flow_name
from core.flow_runner import FlowRunner
from ui.flow_io import FlowIoError, load_flow_into, save_flow_to
from ui.flow_scene import FlowScene
from ui.flow_view import FlowView
from ui.icons import material_icon
from typing_extensions import override

from ui.page import PageBase, ToolbarSection
from ui.dock_layout import restore_dock_layout, save_dock_layout
from ui.node_doc_panel import NodeDocPanel
from ui.node_item import NodeItem
from ui.node_list import NodeList
from ui.node_list_state import restore_node_list_state, save_node_list_state
from ui.recent_flows import RecentFlowsManager
from ui.message_banner import MessageBanner
from ui.flow_status_widget import FlowStatusWidget
from ui.theme import STATUS_MUTED_COLOR, STATUS_OK_COLOR

if TYPE_CHECKING:
    from core.node_registry import NodeRegistry

logger = logging.getLogger(__name__)

_FLOW_FILE_EXTENSION = ".flowjs"
_FLOW_FILE_FILTER    = "Flow (*.flowjs);;All files (*)"


class NodeEditorPage(PageBase):
    """The editor. Central canvas + Node List dock + Node Documentation dock.

    Dockable panels are hosted on an inner QMainWindow so the Node List and
    Node Documentation can be dragged around, floated, tabbed together, or
    closed by the user. Defaults: both stacked on the left, full-height.
    Whatever the user reshapes the docks into is persisted via
    :mod:`ui.dock_layout` and re-applied on the next launch. Toolbar
    actions are exposed via :meth:`page_toolbar_actions` so MainWindow can
    render them in the global toolbar next to the page-selector radio
    group.

    Signal :attr:`title_changed` fires up to MainWindow whenever the active
    flow name changes. The toolbar's right-aligned status slot is owned by
    this page via :class:`FlowStatusWidget` — it shows the app/version by
    default and flips to a spinner + flow/node labels while a run is in
    flight.
    """

    #: Bridge for :mod:`core.notifications` events. The subscriber
    #: callback emits this signal so Qt's auto-connection delivers
    #: it to ``_on_notification`` on the UI thread (queued across
    #: threads), where the banner is safe to mutate. The first arg
    #: is the :class:`core.notifications.Severity` value (str), the
    #: second is the message.
    _notification_received = Signal(str, str)

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
        # that suppresses re-entrant Run clicks.
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

        # Node Documentation dock — read-only Markdown view of the
        # currently selected node's docstring, ports and params. Kept
        # in its own dock so the user can hide / float / re-tab it
        # through the existing dock-layout machinery; the View menu
        # exposes the standard toggleViewAction. Defaults to the
        # left dock area, stacked under the Node List so the two
        # related panels live in the same column. Issue: #187
        self._node_doc_panel = NodeDocPanel()
        self._node_doc_dock = QDockWidget("Node Documentation", self._inner)
        self._node_doc_dock.setObjectName("NodeDocDock")
        self._node_doc_dock.setWidget(self._node_doc_panel)
        self._node_doc_dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        self._inner.addDockWidget(
            Qt.DockWidgetArea.LeftDockWidgetArea, self._node_doc_dock,
        )
        self._inner.splitDockWidget(
            self._node_list_dock, self._node_doc_dock, Qt.Orientation.Vertical,
        )

        # Selection wiring: the panel mirrors whichever selection source
        # last fired. Palette clicks emit a NodeEntry; canvas clicks land
        # via the FlowScene selection signal and are translated here into
        # the underlying node class. A canvas selection takes precedence
        # over a palette click since it represents "the node I'm
        # currently configuring" — the more useful target for the docs.
        self._node_list.entry_selected.connect(self._on_palette_entry_selected)
        self._scene.selectionChanged.connect(self._on_canvas_selection_changed)

        # Actions: reused by both the page menu and the main toolbar.
        self._actions = self._build_actions()
        # The "Selection" section (stack-V, stack-H, group) is hidden
        # while there's no multi-node selection; flag tracks whether
        # it's currently in the toolbar so threshold crossings can
        # trigger a single rebuild instead of one per selection event.
        self._selection_actions_visible: bool = False
        # Stack / group actions need at least two selected nodes; keep
        # them disabled until that is true and toggle them on selection
        # changes.
        self._actions["stack_vertical"].setEnabled(False)
        self._actions["stack_horizontal"].setEnabled(False)
        self._actions["group"].setEnabled(False)
        # Stop is only meaningful while a run is in flight.
        self._actions["stop"].setEnabled(False)
        self._scene.selectionChanged.connect(self._update_selection_actions)

        # Status bar at the bottom of the inner window. The running-flow
        # indicator lives on the main toolbar via FlowStatusWidget; the
        # status bar is kept purely for timestamp/ok messages.
        self._status_bar = QStatusBar(self._inner)
        self._status_label = QLabel("")
        self._status_bar.addWidget(self._status_label, 1)
        self._inner.setStatusBar(self._status_bar)

        # Floating notification banner anchored to the top-right of the
        # page's client area. Used instead of the status bar for messages
        # that can be long and multi-line — supports info / warning / error
        # severities (see :class:`MessageBanner`).
        self._message_banner = MessageBanner(self._inner)

        # Bridge core.notifications → banner. Producers fire on worker
        # threads; the signal carries the payload back to the UI thread
        # via Qt's auto-queued connection.
        self._notification_received.connect(self._on_notification)
        notifications.subscribe(self._forward_notification)

        # Surface interactive-connection errors (type mismatches) in the
        # message banner instead of swallowing them inside FlowScene.
        self._scene.connection_error.connect(self._on_connection_error)
        # Propagate the scene's unsaved-changes state into the toolbar
        # status widget so the user sees "● Unsaved changes" the moment
        # an edit happens, and the row clears on load/save.
        self._scene.dirty_changed.connect(self._flow_status_widget.set_unsaved)

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
        sections = [
            ToolbarSection("Flow", [
                self._actions["run"],
                self._actions["stop"],
                self._actions["save"],
                self._actions["save_as"],
                self._actions["open"],
                self._actions["reload"],
                self._actions["clear"],
            ]),
            ToolbarSection("View", [
                self._actions["fit"],
                self._actions["reset_zoom"],
            ]),
        ]
        # The "Selection" section only makes sense with at least two
        # nodes selected; suppressing it (rather than just disabling
        # its actions) avoids flashing greyed-out buttons in the
        # toolbar most of the time.
        if self._selection_actions_visible:
            sections.append(ToolbarSection("Selection", [
                self._actions["stack_vertical"],
                self._actions["stack_horizontal"],
                self._actions["group"],
            ]))
        return sections

    @override
    def page_status_widget(self) -> QWidget | None:
        # The FlowStatusWidget manages its own idle/running transitions
        # internally, so MainWindow never needs to swap widgets on this
        # page — we hand back the same instance every call.
        return self._flow_status_widget

    def page_menus(self) -> list[QMenu]:
        # Single "Node Editor" menu exposing only entries that are *not*
        # already in the toolbar — currently just the dock visibility
        # toggles. Toolbar actions (Run, Save, Open, Stack, …) are not
        # duplicated here. The menu itself is rebuilt on every
        # activation because QMenu cannot be easily re-parented across
        # hosts.
        menu = QMenu("Node Editor")
        view_menu = menu.addMenu("View")
        view_menu.addAction(self._node_list_dock.toggleViewAction())
        view_menu.addAction(self._node_doc_dock.toggleViewAction())
        return [menu]

    def on_activated(self) -> None:
        # Refresh menu label via title_changed so MainWindow picks up the
        # current flow name.
        self.title_changed.emit(self.page_title())

    # ── Page state persistence (PageBase lifecycle) ────────────────────────────

    @override
    def restore_state(self) -> None:
        """Re-apply persisted dock layout and node-palette section state.

        Issue: #183 (dock layout), #190 (section expand/collapse)
        """
        restore_dock_layout(self._inner)
        states = restore_node_list_state()
        if states is not None:
            self._node_list.restore_section_states(states)

    @override
    def save_state(self) -> None:
        """Persist dock layout and node-palette section expand/collapse state.

        Issue: #183 (dock layout), #190 (section expand/collapse)
        """
        save_dock_layout(self._inner)
        save_node_list_state(self._node_list.get_section_states())

    # ── Public API (called by MainWindow) ──────────────────────────────────────

    def set_flow(self, flow: Flow) -> None:
        """Replace the editor's current flow with a fresh empty one."""

        if self._flow is not None:        
            logger.info(f"Setting active flow to: {flow.name}")
        else:
            logger.info("Setting active flow to: <None>")

        self._flow = flow
        self._scene.set_flow(flow)
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
        # load_flow_into calls set_flow (clears dirty) but then every
        # node/link it re-creates goes through add_node / connect_ports,
        # which flip dirty back on. Reset once the rebuild is done so
        # a freshly-loaded flow starts clean.
        self._scene.mark_saved()
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
            "stop":    mk("Stop",     "stop",        self._on_stop_clicked),
            "save":    mk("Save",     "save",        self._on_save_clicked),
            "save_as": mk("Save As…", "save_as",     self._on_save_as_clicked),
            "open":    mk("Open",     "folder_open", self._on_open_clicked),
            "reload":  mk("Reload",   "refresh",     self._on_reload_clicked),
            "clear":   mk("Clear",    "delete",      self._on_clear_clicked),
            "fit":     mk("Fit",      "zoom_out_map",    self._view.fit_to_contents),
            "reset_zoom": mk("1:1", "fullscreen_exit", self._view.reset_zoom),
            "stack_vertical": mk(
                "V-Stack", "view_stream", self._on_stack_vertical_clicked,
            ),
            "stack_horizontal": mk(
                "H-Stack", "view_column", self._on_stack_horizontal_clicked,
            ),
            "group": mk("Group", "select_all", self._on_group_clicked),
        }

    # ── Action handlers ────────────────────────────────────────────────────────

    def _update_selection_actions(self) -> None:
        """Sync selection-dependent toolbar / menu state with the scene.

        Two things move together:
          - Each selection-gated action's ``enabled`` flag (so menu
            entries grey out cleanly).
          - The "Selection" toolbar section as a whole, which only
            appears at all when there's something to operate on.
            Toggling its visibility goes through
            :attr:`toolbar_layout_changed` so MainWindow rebuilds the
            toolbar instead of leaving an orphan separator.
        """
        selected_nodes = sum(
            1 for s in self._scene.selectedItems() if isinstance(s, NodeItem)
        )
        active = selected_nodes >= 2
        for name in ("stack_vertical", "stack_horizontal", "group"):
            self._actions[name].setEnabled(active)
        if active != self._selection_actions_visible:
            self._selection_actions_visible = active
            self.toolbar_layout_changed.emit()

    def _on_group_clicked(self) -> None:
        self._scene.create_group_around_selection()

    def _on_stack_vertical_clicked(self) -> None:
        """Align selected nodes on a shared X axis and stack them vertically."""
        self._scene.stack_selected_vertically()

    def _on_stack_horizontal_clicked(self) -> None:
        """Align selected nodes on a shared Y axis and stack them horizontally."""
        self._scene.stack_selected_horizontally()

    def _on_palette_entry_selected(self, entry: object | None) -> None:
        """Mirror the palette's selection in the documentation panel.

        Skipped while the canvas already has a selected node — that
        selection represents "the node the user is currently working
        on" and is the more useful target for the docs view. When the
        canvas clears (no node selected), the palette selection takes
        over again on the next palette click.
        """
        if any(isinstance(s, NodeItem) for s in self._scene.selectedItems()):
            return
        if entry is None:
            self._node_doc_panel.clear()
            return
        self._node_doc_panel.show_entry(entry)

    def _on_canvas_selection_changed(self) -> None:
        """Mirror the canvas's selection in the documentation panel.

        Picks the first selected :class:`NodeItem` (multi-select shows
        the docs of the topmost one — Qt's selection order is stable
        per session and the alternative — flipping back to the empty
        state on every multi-select — is more confusing in practice).
        With no node selected, the panel falls back to the empty state
        so a stale class doesn't linger after the user clicks on
        empty canvas.
        """
        node_items = [
            s for s in self._scene.selectedItems() if isinstance(s, NodeItem)
        ]
        if not node_items:
            self._node_doc_panel.clear()
            return
        self._node_doc_panel.show_class(type(node_items[0].node))

    def _on_run_clicked(self) -> None:
        if self._flow is None:
            self._set_status("No flow to run", kind="fail")
            return
        if self._run_thread is not None:
            # A run is already in flight — ignore the click rather than
            # stacking runs on top of each other.
            return

        self._set_toolbar_enabled(False)
        self._set_param_widgets_enabled(False)
        # Stop is only meaningful while a flow is in flight — keep it
        # enabled while every other toolbar action is greyed out.
        self._actions["stop"].setEnabled(True)
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

        self._finalize_run()

    def _on_run_failed(self, detail: str) -> None:
        self._set_status(f"Run failed ({detail})", kind="fail")
        self._finalize_run()

    def _on_stop_clicked(self) -> None:
        """Ask the running flow to stop after its current step.

        No-op when nothing is running. The runner forwards the request
        to :meth:`Flow.request_stop`, which the execution loop polls
        between every interleave step — already-decoded frames flush
        through, then nodes get their normal ``after_run`` cleanup.
        """
        if self._run_runner is None:
            return
        self._actions["stop"].setEnabled(False)
        self._set_status("Stopping…", kind="muted")
        self._run_runner.request_stop()

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

        Covers everything exposed via :meth:`page_toolbar_sections` —
        Run, the file actions and the view actions — so the user can't
        save, open or clear a flow that is still executing on the
        worker thread. ``Stop`` inverts: it is the *only* action
        enabled while a run is in flight; when re-enabling after a
        run, Stop is greyed out instead. When re-enabling,
        ``_update_selection_actions`` re-applies the selection-
        dependent gating for the stack actions instead of leaving
        them unconditionally enabled.
        """
        for name, action in self._actions.items():
            if name == "stop":
                # Inverted polarity: Stop is only useful while running.
                action.setEnabled(not enabled)
            else:
                action.setEnabled(enabled)
        if enabled:
            self._update_selection_actions()

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
        self._scene.mark_saved()
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
        self._scene.mark_saved()
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

    def _on_reload_clicked(self) -> None:
        """Re-read the current flow from disk, discarding unsaved edits.

        Path is reconstructed from ``flow.name`` the same way ``Save``
        does, so Reload is only meaningful for flows that actually live
        in :data:`FLOW_DIR`. A flow that has never been saved (still
        ``Untitled_flow``) or whose file has been removed gets a clear
        error in the status line instead of silently wiping the canvas.
        """
        if self._flow is None:
            self._set_status("No flow to reload", kind="fail")
            return
        path = FLOW_DIR / f"{self._flow.name}{_FLOW_FILE_EXTENSION}"
        if not path.is_file():
            self._set_status(
                f"No saved file to reload at {_display_path(path)}",
                kind="fail",
            )
            return
        # Only nag when there's something to lose. A clean canvas can
        # reload silently — the button doubles as a cheap "refresh from
        # disk" when the file was edited externally.
        if self._scene.is_dirty and QMessageBox.question(
            self, "Discard unsaved changes?",
            f"Reload {path.name} from disk? Unsaved edits will be lost.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        self.load_flow(path)

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
        """Surface a FlowScene connection rejection in the message banner."""
        self._set_status(message, kind="fail")

    # ── Notifications hub ──────────────────────────────────────────────────────

    def _forward_notification(
        self, severity: notifications.Severity, message: str,
    ) -> None:
        """Subscriber for ``core.notifications``; runs on the producer's thread.

        Just hops the payload across the signal so the actual banner
        update happens on the UI thread.
        """
        self._notification_received.emit(severity.value, message)

    @Slot(str, str)
    def _on_notification(self, severity_value: str, message: str) -> None:
        """UI-thread slot that pops the toast for a hub notification."""
        if severity_value == notifications.Severity.ERROR.value:
            self._message_banner.show_error(message)
        elif severity_value == notifications.Severity.INFO.value:
            self._message_banner.show_info(message)
        else:
            self._message_banner.show_warning(message)

    # ── Status line ────────────────────────────────────────────────────────────

    def _set_status(self, message: str, *, kind: str) -> None:
        # Failures go to the floating message banner (red) so long /
        # multi-line messages are readable. The status bar keeps the
        # last success or informational message so the user can still
        # glance at it.
        if kind == "fail":
            self._message_banner.show_error(message)
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
            self._message_banner.hide()


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

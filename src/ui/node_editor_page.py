from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QStatusBar,
    QStyle,
    QVBoxLayout,
)

from constants import FLOW_DIR
from core.flow import Flow, is_valid_flow_name
from ui.flow_io import FlowIoError, load_flow_into, save_flow_to
from ui.flow_scene import FlowScene
from ui.flow_view import FlowView
from ui.page import Page
from ui.palette_widget import PaletteWidget
from ui.theme import STATUS_FAIL_COLOR, STATUS_MUTED_COLOR, STATUS_OK_COLOR
from ui.viewer_panel import ViewerPanel

if TYPE_CHECKING:
    from core.node_registry import NodeRegistry

logger = logging.getLogger(__name__)

_FLOW_FILE_EXTENSION = ".flowjs"
_FLOW_FILE_FILTER    = "Flow (*.flowjs);;All files (*)"


class NodeEditorPage(Page):
    """The editor. Central canvas + palette dock (left) + viewer dock (bottom).

    Dockable panels are hosted on an inner QMainWindow so the palette and
    viewer can be dragged around, floated, or closed by the user. Toolbar
    actions are exposed via :meth:`page_toolbar_actions` so MainWindow can
    render them in the global toolbar next to the page-selector radio group.

    Signal :attr:`title_changed` fires up to MainWindow whenever the active
    flow name changes.
    """

    def __init__(self, registry: NodeRegistry) -> None:
        super().__init__()
        self._registry = registry
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

        # Palette dock (left).
        self._palette = PaletteWidget(registry)
        self._palette_dock = QDockWidget("Palette", self._inner)
        self._palette_dock.setObjectName("PaletteDock")
        self._palette_dock.setWidget(self._palette)
        self._palette_dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        self._inner.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._palette_dock)

        # Viewer dock (bottom).
        self._viewer = ViewerPanel()
        self._viewer_dock = QDockWidget("Viewer", self._inner)
        self._viewer_dock.setObjectName("ViewerDock")
        self._viewer_dock.setWidget(self._viewer)
        self._viewer_dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        self._inner.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._viewer_dock)

        # Actions: reused by both the page menu and the main toolbar.
        self._actions = self._build_actions()

        # Status bar at the bottom of the inner window.
        self._status_bar = QStatusBar(self._inner)
        self._status_label = QLabel("")
        self._status_bar.addWidget(self._status_label, 1)
        self._inner.setStatusBar(self._status_bar)

        # Wire scene → viewer.
        self._scene.selected_node_changed.connect(self._viewer.show_node)

    # ── Page hooks ─────────────────────────────────────────────────────────────

    def page_title(self) -> str:
        # Return just the flow name (or empty) so MainWindow renders a
        # title like "Sparklehoof — MyFlow" rather than embedding the
        # page's role in the window caption.
        if self._flow is not None:
            return self._flow.name
        return ""

    def page_selector_label(self) -> str:
        return "Editor"

    def page_selector_icon(self) -> QIcon:
        return self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogListView)

    def page_toolbar_actions(self) -> list[QAction]:
        return [
            self._actions["run"],
            self._actions["save"],
            self._actions["save_as"],
            self._actions["open"],
            self._actions["clear"],
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
        view_menu.addAction(self._palette_dock.toggleViewAction())
        view_menu.addAction(self._viewer_dock.toggleViewAction())
        return [menu]

    def on_activated(self) -> None:
        # Refresh menu label via title_changed so MainWindow picks up the
        # current flow name. Also refresh the viewer to whatever is
        # currently selected (nothing, typically).
        self.title_changed.emit(self.page_title())
        self._viewer.refresh()

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
        self._set_status(
            f"Loaded {_display_path(path)} at {datetime.now().strftime('%H:%M:%S')}",
            kind="ok",
        )
        return True

    # ── Actions ────────────────────────────────────────────────────────────────

    def _build_actions(self) -> dict[str, QAction]:
        style = self.style()

        def mk(text: str, icon_id: QStyle.StandardPixmap, slot) -> QAction:
            a = QAction(style.standardIcon(icon_id), text, self)
            a.triggered.connect(slot)
            return a

        return {
            "run":     mk("Run",      QStyle.StandardPixmap.SP_MediaPlay,        self._on_run_clicked),
            "save":    mk("Save",     QStyle.StandardPixmap.SP_DialogSaveButton, self._on_save_clicked),
            "save_as": mk("Save As…", QStyle.StandardPixmap.SP_DriveFDIcon,      self._on_save_as_clicked),
            "open":    mk("Open",     QStyle.StandardPixmap.SP_DirOpenIcon,      self._on_open_clicked),
            "clear":   mk("Clear",    QStyle.StandardPixmap.SP_TrashIcon,        self._on_clear_clicked),
        }

    # ── Action handlers ────────────────────────────────────────────────────────

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
        self._viewer.refresh()

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

    # ── Status line ────────────────────────────────────────────────────────────

    def _set_status(self, message: str, *, kind: str) -> None:
        color = {
            "ok":    STATUS_OK_COLOR,
            "fail":  STATUS_FAIL_COLOR,
            "muted": STATUS_MUTED_COLOR,
        }.get(kind, STATUS_MUTED_COLOR)
        self._status_label.setText(message)
        # Show the full message in a tooltip so long exception text isn't
        # lost when the status bar truncates the label.
        self._status_label.setToolTip(message)
        self._status_label.setStyleSheet(
            f"color: rgb({color.red()},{color.green()},{color.blue()});"
        )


# ── Helpers ────────────────────────────────────────────────────────────────────

def _display_path(path: Path) -> str:
    """Return ``path`` relative to cwd when possible, otherwise absolute."""
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)

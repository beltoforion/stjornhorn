from __future__ import annotations

import importlib
import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QGraphicsProxyWidget,
    QGraphicsScene,
    QGraphicsSceneContextMenuEvent,
    QGraphicsSceneMouseEvent,
    QMenu,
)

from core.flow import Flow
from core.node_base import NodeBase
from ui.backdrop_item import BACKDROP_PRESETS, BackdropItem
from ui.link_item import LinkItem, PendingLinkItem
from ui.node_item import NodeItem
from ui.port_item import PortItem

if TYPE_CHECKING:
    from core.node_registry import NodeEntry

logger = logging.getLogger(__name__)


class FlowScene(QGraphicsScene):
    """Graphics scene mediating between the ``Flow`` model and its visual.

    Owns every :class:`NodeItem` and :class:`LinkItem`. Handles:

      - drag-from-palette drops → instantiating the right NodeBase and
        registering it with the active Flow.
      - drag-between-ports → creating both the visual LinkItem and the
        underlying ``Flow.connect`` edge.
      - right-click context menu on links (Delete). Nodes are deleted
        via the ``X`` button in their header or the Delete key.

    Emits :attr:`selected_node_changed` whenever the user's selection
    settles on a different single node (None when nothing or multiple
    things are selected).
    """

    selected_node_changed = Signal(object)   # NodeBase | None
    #: Emitted when any parameter widget on any node in the scene changes value.
    param_changed = Signal()
    #: Emitted when an interactive connection attempt raises a user-actionable
    #: error (e.g. incompatible port types). Carries the exception's message so
    #: the host page can surface it in the error banner.
    connection_error = Signal(str)
    #: Emitted when the scene's unsaved-changes state transitions. Carries the
    #: new value of :attr:`is_dirty` so listeners can update UI without polling.
    dirty_changed = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self._flow: Flow | None = None
        self._node_items: dict[int, NodeItem] = {}          # id(node_base) → NodeItem
        self._links: list[LinkItem] = []
        self._backdrops: list[BackdropItem] = []
        self._pending_link: PendingLinkItem | None = None
        self._pending_src_port: PortItem | None = None
        self._last_emitted_selected: NodeBase | None = None
        self._dirty: bool = False

        self.selectionChanged.connect(self._on_selection_changed)
        # Every param-widget edit is an unsaved change. Structural edits
        # (add/remove node, add/remove link, layout stack, flow rename)
        # call _mark_dirty directly from the method that performs them.
        self.param_changed.connect(self._mark_dirty)

    # ── Flow binding ───────────────────────────────────────────────────────────

    def set_flow(self, flow: Flow) -> None:
        """Replace the current flow and wipe the canvas.

        A freshly-set flow starts clean: whatever the caller just loaded
        (or created) is, by definition, "saved" — any subsequent edit
        will flip the scene back to dirty.
        """
        self.clear_scene()
        self._flow = flow
        self._set_dirty(False)

    @property
    def flow(self) -> Flow | None:
        return self._flow

    def clear_scene(self) -> None:
        """Remove every item and Flow connection. The Flow itself is left
        in place by the caller (use :meth:`set_flow` to swap)."""
        for link in list(self._links):
            self._delete_link_item(link)
        for item in list(self._node_items.values()):
            self._delete_node_item(item)
        for backdrop in list(self._backdrops):
            self.removeItem(backdrop)
        self._node_items.clear()
        self._links.clear()
        self._backdrops.clear()
        self._pending_link = None
        self._pending_src_port = None
        self._last_emitted_selected = None

    # ── Node operations ────────────────────────────────────────────────────────

    def add_node(self, node: NodeBase, scene_pos: QPointF | None = None) -> NodeItem:
        item = NodeItem(node)
        item.signals.param_changed.connect(self.param_changed)
        self.addItem(item)
        if scene_pos is not None:
            item.setPos(scene_pos)
        self._node_items[id(node)] = item
        if self._flow is not None:
            self._flow.add_node(node)
        self._mark_dirty()
        return item

    def instantiate_and_add(self, entry: NodeEntry, scene_pos: QPointF | None = None) -> NodeItem | None:
        """Import the class referenced by ``entry`` and add an instance."""
        try:
            module = importlib.import_module(entry.module)
            cls    = getattr(module, entry.class_name)
            node   = cls()
        except Exception:
            logger.exception("Failed to instantiate %s.%s", entry.module, entry.class_name)
            return None
        logger.debug("Adding node '%s'", node.display_name)
        return self.add_node(node, scene_pos)

    def remove_node_item(self, item: NodeItem) -> None:
        """Remove a node and every link attached to its ports."""
        # Delete attached links first so Flow.disconnect runs cleanly.
        for port in [*item.input_ports, *item.output_ports]:
            for link in list(port.links):
                self._delete_link_item(link)
        self._delete_node_item(item)

    # ── Layout helpers ─────────────────────────────────────────────────────────

    STACK_GAP: float = 16.0

    def stack_selected_vertically(self) -> int:
        """Align selected nodes on a single X axis and stack them vertically.

        Preserves the current top-to-bottom order (nodes higher on the canvas
        stay on top in the new stack). All selected nodes are anchored to the
        leftmost selected X so they share a vertical axis; each subsequent
        node is placed beneath the previous one with a fixed :data:`STACK_GAP`
        between their bounding boxes. Returns the number of nodes that were
        moved (two or more selected nodes required — otherwise a no-op).
        """
        items = [s for s in self.selectedItems() if isinstance(s, NodeItem)]
        if len(items) < 2:
            return 0
        items.sort(key=lambda it: it.pos().y())
        x = min(it.pos().x() for it in items)
        y = items[0].pos().y()
        for item in items:
            item.setPos(x, y)
            item.refresh_all_links()
            y += item.boundingRect().height() + self.STACK_GAP
        self._mark_dirty()
        return len(items)

    def stack_selected_horizontally(self) -> int:
        """Align selected nodes on a single Y axis and stack them horizontally.

        Preserves the current left-to-right order (nodes further left on the
        canvas stay left in the new stack). All selected nodes are anchored
        to the topmost selected Y so they share a horizontal axis; each
        subsequent node is placed to the right of the previous one with a
        fixed :data:`STACK_GAP` between their bounding boxes. Returns the
        number of nodes that were moved (two or more selected nodes required
        — otherwise a no-op).
        """
        items = [s for s in self.selectedItems() if isinstance(s, NodeItem)]
        if len(items) < 2:
            return 0
        items.sort(key=lambda it: it.pos().x())
        y = min(it.pos().y() for it in items)
        x = items[0].pos().x()
        for item in items:
            item.setPos(x, y)
            item.refresh_all_links()
            x += item.boundingRect().width() + self.STACK_GAP
        self._mark_dirty()
        return len(items)

    def _delete_node_item(self, item: NodeItem) -> None:
        if self._flow is not None:
            try:
                self._flow.remove_node(item.node)
            except ValueError:
                pass
        self._node_items.pop(id(item.node), None)
        self.removeItem(item)
        self._mark_dirty()

    # ── Link operations ────────────────────────────────────────────────────────

    def connect_ports(self, src: PortItem, dst: PortItem) -> LinkItem | None:
        """Create a link from ``src`` (output) to ``dst`` (input).

        Returns ``None`` for trivial rejections (wrong direction, self-loop,
        duplicate) and raises :class:`TypeError` when the underlying
        :meth:`Flow.connect` rejects the edge as type-incompatible. Callers
        are expected to surface that error to the user (the interactive
        drag path in :meth:`mouseReleaseEvent` emits
        :attr:`connection_error`; the flow-loader in ``flow_io`` logs and
        skips the edge).
        """
        if src.kind != "output" or dst.kind != "input":
            return None
        if src.node_item is dst.node_item:
            return None  # no self-loops
        if any(link for link in src.links if link.dst_port is dst):
            return None  # duplicate

        src_node = src.node_item.node
        dst_node = dst.node_item.node
        if self._flow is not None:
            self._flow.connect(src_node, src.index, dst_node, dst.index)

        link = LinkItem(src, dst)
        self.addItem(link)
        self._links.append(link)
        self._mark_dirty()
        return link

    def _delete_link_item(self, link: LinkItem) -> None:
        if self._flow is not None:
            try:
                self._flow.disconnect(
                    link.src_port.node_item.node, link.src_port.index,
                    link.dst_port.node_item.node, link.dst_port.index,
                )
            except Exception:
                logger.debug("Flow.disconnect failed on link delete", exc_info=True)
        link.detach()
        if link in self._links:
            self._links.remove(link)
        self.removeItem(link)
        self._mark_dirty()

    # ── Backdrops ──────────────────────────────────────────────────────────────

    def add_backdrop(
        self,
        scene_pos: QPointF | None = None,
        *,
        title: str = "Backdrop",
        width: float | None = None,
        height: float | None = None,
        color=None,
        capture_active: bool = False,
    ) -> BackdropItem:
        """Add a :class:`BackdropItem` to the scene and mark dirty.

        Keyword arguments with ``None`` defaults let the caller pass
        explicit geometry (e.g. from a deserialised flow) without
        forcing every call site to re-import the defaults module.
        """
        kwargs: dict = {"title": title, "capture_active": capture_active}
        if width is not None:
            kwargs["width"] = width
        if height is not None:
            kwargs["height"] = height
        if color is not None:
            kwargs["color"] = color
        backdrop = BackdropItem(**kwargs)
        self.addItem(backdrop)
        if scene_pos is not None:
            backdrop.setPos(scene_pos)
        self._backdrops.append(backdrop)
        self._mark_dirty()
        return backdrop

    def remove_backdrop(self, backdrop: BackdropItem) -> None:
        if backdrop in self._backdrops:
            self._backdrops.remove(backdrop)
        self.removeItem(backdrop)
        self._mark_dirty()

    def iter_backdrops(self) -> list[BackdropItem]:
        """Return a snapshot of every backdrop currently in the scene."""
        return list(self._backdrops)

    # ── Pending-link drag ──────────────────────────────────────────────────────

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:  # type: ignore[override]
        from PySide6.QtCore import Qt
        if event.button() == Qt.MouseButton.LeftButton:
            port = self._port_at(event.scenePos())
            if port is not None:
                # Start a pending link from this port. Swallow the press
                # so that neither the port nor the underlying node grabs
                # the mouse — we want subsequent move / release events to
                # reach the scene itself.
                self._pending_src_port = port
                self._pending_link = PendingLinkItem(port.scenePos())
                self._pending_link.update_end(event.scenePos())
                self.addItem(self._pending_link)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:  # type: ignore[override]
        if self._pending_link is not None:
            self._pending_link.update_end(event.scenePos())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:  # type: ignore[override]
        if self._pending_link is not None and self._pending_src_port is not None:
            target = self._port_at(event.scenePos())
            self.removeItem(self._pending_link)
            self._pending_link = None
            src = self._pending_src_port
            self._pending_src_port = None

            if target is not None and target is not src:
                # Allow drag from either direction (output→input or input→output).
                try:
                    if src.kind == "output" and target.kind == "input":
                        self.connect_ports(src, target)
                    elif src.kind == "input" and target.kind == "output":
                        self.connect_ports(target, src)
                except TypeError as err:
                    # Surface incompatible-port errors through the UI so
                    # the user sees why the edge was rejected.
                    self.connection_error.emit(str(err))
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _port_at(self, scene_pos: QPointF) -> PortItem | None:
        for item in self.items(scene_pos):
            if isinstance(item, PortItem):
                return item
        return None

    # ── Context menus ──────────────────────────────────────────────────────────

    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent) -> None:  # type: ignore[override]
        from PySide6.QtGui import QTransform
        views = self.views()
        xform = views[0].transform() if views else QTransform()
        raw_item = self.itemAt(event.scenePos(), xform)
        # Walk up the parent chain so right-clicking a title / grip on
        # a backdrop hits the BackdropItem, and right-clicking a link
        # label hits the LinkItem.
        item = raw_item
        while item is not None:
            if isinstance(item, (LinkItem, BackdropItem)):
                break
            item = item.parentItem()

        if isinstance(item, LinkItem):
            self._link_context_menu(item, event)
            return
        if isinstance(item, BackdropItem):
            self._backdrop_context_menu(item, event)
            return
        # Empty canvas → offer Add Backdrop.
        if raw_item is None:
            self._canvas_context_menu(event)
            return
        super().contextMenuEvent(event)

    def _link_context_menu(self, link: LinkItem, event: QGraphicsSceneContextMenuEvent) -> None:
        menu = QMenu()
        delete = QAction("Delete Connection", menu)
        delete.triggered.connect(lambda: self._delete_link_item(link))
        menu.addAction(delete)
        menu.exec(event.screenPos())

    def _canvas_context_menu(self, event: QGraphicsSceneContextMenuEvent) -> None:
        menu = QMenu()
        add = QAction("Add Backdrop", menu)
        scene_pos = event.scenePos()
        add.triggered.connect(lambda: self.add_backdrop(scene_pos))
        menu.addAction(add)
        menu.exec(event.screenPos())

    def _backdrop_context_menu(
        self, backdrop: BackdropItem, event: QGraphicsSceneContextMenuEvent,
    ) -> None:
        menu = QMenu()

        rename = QAction("Rename…", menu)
        rename.triggered.connect(lambda: self._prompt_rename_backdrop(backdrop))
        menu.addAction(rename)

        colour_menu = menu.addMenu("Colour")
        for name, colour in BACKDROP_PRESETS.items():
            act = QAction(name, colour_menu)
            act.triggered.connect(
                lambda _checked=False, c=colour: self._recolour_backdrop(backdrop, c)
            )
            colour_menu.addAction(act)

        menu.addSeparator()
        delete = QAction("Delete Backdrop", menu)
        delete.triggered.connect(lambda: self.remove_backdrop(backdrop))
        menu.addAction(delete)

        menu.exec(event.screenPos())

    def _prompt_rename_backdrop(self, backdrop: BackdropItem) -> None:
        """Pop a tiny dialog to rename the backdrop.

        Kept in the scene rather than on the backdrop item itself so
        the input-dialog-vs-inline-edit decision can change later
        without touching every BackdropItem.
        """
        from PySide6.QtWidgets import QInputDialog
        views = self.views()
        parent = views[0] if views else None
        new_title, ok = QInputDialog.getText(
            parent, "Rename Backdrop", "Title:", text=backdrop.title,
        )
        if ok and new_title != backdrop.title:
            backdrop.set_title(new_title)
            self._mark_dirty()

    def _recolour_backdrop(self, backdrop: BackdropItem, colour) -> None:
        backdrop.set_color(colour)
        self._mark_dirty()

    # ── Selection → signal ─────────────────────────────────────────────────────

    def _on_selection_changed(self) -> None:
        selected = self.selectedItems()
        node_items = [s for s in selected if isinstance(s, NodeItem)]
        node = node_items[0].node if len(node_items) == 1 else None
        if node is not self._last_emitted_selected:
            self._last_emitted_selected = node
            self.selected_node_changed.emit(node)

    # ── Iteration helpers used by flow_io ──────────────────────────────────────

    def iter_node_items(self) -> list[NodeItem]:
        return list(self._node_items.values())

    def node_item_for(self, node: NodeBase) -> NodeItem | None:
        return self._node_items.get(id(node))

    def iter_links(self) -> list[LinkItem]:
        return list(self._links)

    # ── Dirty tracking ─────────────────────────────────────────────────────────

    @property
    def is_dirty(self) -> bool:
        """True if the scene has been modified since the last save/load."""
        return self._dirty

    def mark_saved(self) -> None:
        """Reset the dirty flag. Called by the editor after a successful save."""
        self._set_dirty(False)

    def mark_dirty(self) -> None:
        """Flag the scene as modified.

        Exposed for edits the scene can't observe on its own — most
        notably renaming the underlying :class:`Flow` from the host
        page. Structural edits performed via scene methods already
        call this internally.
        """
        self._mark_dirty()

    def _mark_dirty(self) -> None:
        self._set_dirty(True)

    def _set_dirty(self, value: bool) -> None:
        if self._dirty == value:
            return
        self._dirty = value
        self.dirty_changed.emit(value)

    # ── Keyboard ───────────────────────────────────────────────────────────────

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        from PySide6.QtCore import Qt
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            # If an embedded Qt widget (e.g. a node's path QLineEdit) holds
            # focus, forward the key so the user can actually delete text.
            # Otherwise Delete/Backspace would be swallowed here and the
            # widget never sees it — instead deleting the selected node.
            if isinstance(self.focusItem(), QGraphicsProxyWidget):
                super().keyPressEvent(event)
                return
            for s in list(self.selectedItems()):
                if isinstance(s, NodeItem):
                    self.remove_node_item(s)
                elif isinstance(s, LinkItem):
                    self._delete_link_item(s)
                elif isinstance(s, BackdropItem):
                    self.remove_backdrop(s)
            event.accept()
            return
        super().keyPressEvent(event)

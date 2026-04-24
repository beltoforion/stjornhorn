from __future__ import annotations

import importlib
import json
import logging

from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING
from constants import APP_VERSION
from core.flow import Flow
from core.node_base import NodeBase

if TYPE_CHECKING:
    from ui.flow_scene import FlowScene

logger = logging.getLogger(__name__)

FLOW_FORMAT_VERSION: int = 1

# Legacy (module, class) → current (module, class) remaps applied at load
# time. Lets older saved flows keep working after a node is renamed,
# without forcing users to re-save every file. Keep the list small and
# well-commented — each entry is a one-off migration, not a long-term
# alias.
_LEGACY_NODE_REMAPS: dict[tuple[str, str], tuple[str, str]] = {
    # v0.1.14: RGB Split/Join were superseded by RGBA-aware variants
    # with an extra (optional) alpha channel — see issue #142.
    ("nodes.filters.rgb_split", "RgbSplit"): ("nodes.filters.rgba_split", "RgbaSplit"),
    ("nodes.filters.rgb_join",  "RgbJoin"):  ("nodes.filters.rgba_join",  "RgbaJoin"),
}


class FlowIoError(Exception):
    """Raised when a flow file cannot be read, parsed, or version-matched."""


def serialize_flow(scene: FlowScene, flow: Flow) -> dict:
    """ Return a JSON-compatible snapshot of ``flow`` as shown in ``scene``.
    """
    
    node_items = scene.iter_node_items()
    node_ids = {id(item.node): idx for idx, item in enumerate(node_items)}

    nodes_out: list[dict] = []
    for idx, item in enumerate(node_items):
        pos = item.pos()
        node = item.node
        params = {p.name: _jsonable(getattr(node, p.name, None)) for p in node.params}
        entry: dict = {
            "id":       idx,
            "module":   type(node).__module__,
            "class":    type(node).__name__,
            "position": [float(pos.x()), float(pos.y())],
            "params":   params,
        }
        user_w, user_h = item.user_size
        if user_w is not None or user_h is not None:
            # Persist both axes even when only one is user-set so the
            # load side can round-trip without needing null sentinels.
            entry["size"] = [float(item.width), float(item.body_height)]
        if node.skipped:
            entry["skipped"] = True
        nodes_out.append(entry)

    connections_out: list[dict] = []
    for link in scene.iter_links():
        src_node = link.src_port.node_item.node
        dst_node = link.dst_port.node_item.node
        connections_out.append({
            "src_node":   node_ids[id(src_node)],
            "src_output": link.src_port.index,
            "dst_node":   node_ids[id(dst_node)],
            "dst_input":  link.dst_port.index,
        })

    backdrops_out: list[dict] = []
    for backdrop in scene.iter_backdrops():
        pos = backdrop.pos()
        colour = backdrop.color
        backdrops_out.append({
            "position": [float(pos.x()), float(pos.y())],
            "size":     [float(backdrop.width), float(backdrop.height)],
            "title":    backdrop.title,
            "color":    [colour.red(), colour.green(), colour.blue(), colour.alpha()],
        })

    return {
        "version":     FLOW_FORMAT_VERSION,
        "app_version": APP_VERSION,
        "name":        flow.name,
        "nodes":       nodes_out,
        "connections": connections_out,
        "backdrops":   backdrops_out,
    }


def save_flow_to(path: Path, scene: FlowScene, flow: Flow) -> None:
    """Serialize ``flow`` and write it to ``path`` as pretty-printed JSON."""
    data = serialize_flow(scene, flow)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_flow_into(path: Path, scene: FlowScene) -> Flow:
    """Replace the contents of ``scene`` with the flow stored at ``path``.

    Raises :class:`FlowIoError` on I/O / parse failure or on an
    unsupported format version. Returns the freshly-created :class:`Flow`
    (with its restored name) so the caller can hand it to
    :meth:`scene.set_flow` *after* passing unit tests for the file, etc.
    """

    logger.info(f'Loading flow from "{path}"')
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)        
    except OSError as err:
        raise FlowIoError(f"Cannot read file: {err}") from err
    except json.JSONDecodeError as err:
        raise FlowIoError(f"Invalid JSON: {err}") from err

    version = data.get("version")
    if version != FLOW_FORMAT_VERSION:
        raise FlowIoError(f"Unsupported format version: {version!r}")

    from PySide6.QtCore import QPointF

    flow = Flow(name=data.get("name", path.stem))
    scene.set_flow(flow)

    id_to_node: dict[int, NodeBase] = {}
    for entry in data.get("nodes", []):
        node = _instantiate_node(entry)
        if node is None:
            continue

        pos = entry.get("position") or [0.0, 0.0]
        scene.add_node(node, QPointF(float(pos[0]), float(pos[1])))
        id_to_node[entry["id"]] = node

        size = entry.get("size")
        if size:
            item = scene.node_item_for(node)
            if item is not None:
                item.apply_user_size(float(size[0]), float(size[1]))

    for conn in data.get("connections", []):
        src = id_to_node.get(conn.get("src_node"))
        dst = id_to_node.get(conn.get("dst_node"))

        if src is None or dst is None:
            logger.debug(f"Skipping connection with unknown endpoint: {conn}")
            continue

        src_item = scene.node_item_for(src)
        dst_item = scene.node_item_for(dst)
        if src_item is None or dst_item is None:
            continue

        try:
            src_port = src_item.output_port(conn["src_output"])
            dst_port = dst_item.input_port(conn["dst_input"])
            scene.connect_ports(src_port, dst_port)
        except (IndexError, KeyError):
            logger.warning(f"Skipping connection with out-of-range port index: {conn}")
            continue
        except TypeError as err:
            # Incompatible port types (e.g. a saved flow routing IMAGE_GREY
            # into an IMAGE-only port). Log and continue so the rest of the
            # flow still loads rather than aborting the whole file.
            logger.warning(f"Skipping incompatible connection {conn}: {err}")

    for entry in data.get("backdrops", []):
        pos = entry.get("position") or [0.0, 0.0]
        size = entry.get("size") or [None, None]
        col_rgba = entry.get("color")
        colour = None
        if col_rgba and len(col_rgba) >= 3:
            from PySide6.QtGui import QColor
            alpha = col_rgba[3] if len(col_rgba) >= 4 else 255
            colour = QColor(
                int(col_rgba[0]), int(col_rgba[1]), int(col_rgba[2]), int(alpha),
            )
        scene.add_backdrop(
            QPointF(float(pos[0]), float(pos[1])),
            title=str(entry.get("title", "Backdrop")),
            width=float(size[0]) if size[0] is not None else None,
            height=float(size[1]) if size[1] is not None else None,
            color=colour,
        )

    return flow

# ── Helpers ────────────────────────────────────────────────────────────────────

def _instantiate_node(entry: dict) -> NodeBase | None:
    """Construct a NodeBase from a serialized node entry.

    Returns None (and logs) if the module/class is unknown, so loading
    can proceed with the remaining nodes instead of failing the whole
    flow.
    """

    module_name = entry.get("module", "")
    class_name  = entry.get("class",  "")

    remap = _LEGACY_NODE_REMAPS.get((module_name, class_name))
    if remap is not None:
        logger.info(
            f"Remapping legacy node {module_name}.{class_name} → "
            f"{remap[0]}.{remap[1]}"
        )
        module_name, class_name = remap

    try:
        module = importlib.import_module(module_name)
        cls    = getattr(module, class_name)
        node: NodeBase = cls()
    except Exception:
        logger.exception(f"Failed to instantiate {module_name}.{class_name}")
        return None

    for name, value in (entry.get("params") or {}).items():
        try:
            setattr(node, name, value)
        except Exception:
            logger.warning(f"Ignoring param {name} on {module_name}.{class_name} ({value!r})")

    if entry.get("skipped"):
        try:
            node.skipped = True
        except Exception:
            logger.warning(f"Ignoring skipped flag on {module_name}.{class_name}")

    return node


def _jsonable(value: object) -> object:
    """Coerce ``value`` to a JSON-serialisable form (recursive for containers)."""

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, Enum):
        # Persist the underlying value (e.g. IntEnum → int, str-backed Enum
        # → str) so the node setter can reconstruct the member on load,
        # and saved flows stay human-readable.
        return _jsonable(value.value)

    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]

    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}

    return value

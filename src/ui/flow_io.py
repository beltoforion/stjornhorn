from __future__ import annotations

import importlib
import json
import logging
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from core.flow import Flow
from core.node_base import NodeBase

if TYPE_CHECKING:
    from ui.flow_scene import FlowScene

logger = logging.getLogger(__name__)

FLOW_FORMAT_VERSION: int = 1


class FlowIoError(Exception):
    """Raised when a flow file cannot be read, parsed, or version-matched."""


def serialize_flow(scene: FlowScene, flow: Flow) -> dict:
    """Return a JSON-compatible snapshot of ``flow`` as shown in ``scene``."""
    node_items = scene.iter_node_items()
    node_ids = {id(item.node): idx for idx, item in enumerate(node_items)}

    nodes_out: list[dict] = []
    for idx, item in enumerate(node_items):
        pos = item.pos()
        node = item.node
        params = {p.name: _jsonable(getattr(node, p.name, None)) for p in node.params}
        nodes_out.append({
            "id":       idx,
            "module":   type(node).__module__,
            "class":    type(node).__name__,
            "position": [float(pos.x()), float(pos.y())],
            "params":   params,
        })

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

    return {
        "version":     FLOW_FORMAT_VERSION,
        "name":        flow.name,
        "nodes":       nodes_out,
        "connections": connections_out,
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
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as err:
        raise FlowIoError(f"Cannot read file: {err}") from err
    try:
        data = json.loads(raw)
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

    for conn in data.get("connections", []):
        src = id_to_node.get(conn.get("src_node"))
        dst = id_to_node.get(conn.get("dst_node"))
        if src is None or dst is None:
            logger.debug("Skipping connection with unknown endpoint: %s", conn)
            continue
        src_item = scene.node_item_for(src)
        dst_item = scene.node_item_for(dst)
        if src_item is None or dst_item is None:
            continue
        try:
            src_port = src_item.output_port(conn["src_output"])
            dst_port = dst_item.input_port(conn["dst_input"])
        except (IndexError, KeyError):
            logger.warning("Skipping connection with out-of-range port index: %s", conn)
            continue
        scene.connect_ports(src_port, dst_port)

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
    try:
        module = importlib.import_module(module_name)
        cls    = getattr(module, class_name)
    except (ImportError, AttributeError):
        logger.exception("Cannot resolve node %s.%s", module_name, class_name)
        return None

    try:
        node: NodeBase = cls()
    except Exception:
        logger.exception("Failed to instantiate %s.%s", module_name, class_name)
        return None

    for name, value in (entry.get("params") or {}).items():
        try:
            setattr(node, name, value)
        except Exception:
            logger.warning("Ignoring param %s on %s.%s (%r)",
                           name, module_name, class_name, value)
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

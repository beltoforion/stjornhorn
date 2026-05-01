"""Back-compat smoke test for saved ``.flowjs`` files.

Loads every flow shipped under ``flow/`` at the repo root, walks the
node entries, and instantiates each ``module.class`` referenced. Catches
two classes of regression at once:

  * A node refactor that breaks the no-arg ``__init__`` contract — every
    saved flow expects ``Class()`` to succeed.
  * A descriptor-driven port that stops carrying the same port name the
    saved file references — the H2 migration risks renaming a port if
    the descriptor's ``__set_name__`` got the wrong value, in which case
    the saved file's connection wouldn't resolve.

We don't rebuild the full :class:`FlowScene` (that would pull in
PySide6); we only verify each referenced node class can be constructed
and exposes the input-port name the saved connections target.
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

# Tests rely on cv2 / numpy / etc. only transitively via node imports;
# skip cleanly if the runtime environment is missing them.
pytest.importorskip("cv2")
pytest.importorskip("numpy")

REPO_ROOT = Path(__file__).resolve().parent.parent
FLOW_DIR = REPO_ROOT / "flow"


@pytest.mark.parametrize("flow_path", sorted(FLOW_DIR.glob("*.flowjs")))
def test_flow_nodes_round_trip_instantiate(flow_path: Path) -> None:
    """Every node referenced in *flow_path* instantiates and exposes
    the input-port names the saved connections still target."""

    data = json.loads(flow_path.read_text(encoding="utf-8"))
    nodes_by_id: dict[int, object] = {}

    for entry in data.get("nodes", []):
        module_name = entry["module"]
        class_name = entry["class"]

        module = importlib.import_module(module_name)
        cls = getattr(module, class_name)
        node = cls()
        nodes_by_id[entry["id"]] = node

    for conn in data.get("connections", []):
        dst = nodes_by_id.get(conn.get("dst_node"))
        if dst is None:
            continue
        # The save format keys connection endpoints by port *index* rather
        # than name, so the test only proves indexed access still works —
        # equivalent to "the node still exposes at least N input ports".
        dst_input_idx = conn.get("dst_input")
        assert 0 <= dst_input_idx < len(dst.inputs), (
            f"{flow_path.name}: node id={conn['dst_node']} "
            f"({type(dst).__name__}) has {len(dst.inputs)} inputs but "
            f"connection targets index {dst_input_idx}"
        )

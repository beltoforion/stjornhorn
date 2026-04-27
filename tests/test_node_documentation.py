"""Documentation lint for node classes.

These tests enforce the metadata schema declared in :mod:`core.node_doc`
across every built-in node. Most of them are currently
:py:func:`pytest.mark.xfail`-marked because the existing 43-node corpus
predates the schema and a bulk sweep is needed to fill in
``description``, enum mappings, and similar fields. The xfail mark
keeps CI green while still surfacing the requirement; nodes that have
been brought up to spec produce ``XPASS`` rather than passing silently,
giving a visible progress signal during the sweep.

Once the sweep PRs (tracked under issue #187) are complete, the xfail
decorators here come off and the lint becomes a hard gate on every
future node.
"""
from __future__ import annotations

import importlib

import pytest

from constants import BUILTIN_NODES_DIR
from core.node_base import NodeParamType
from core.node_doc import describe_node
from core.node_registry import NodeRegistry


def _all_node_classes() -> list[type]:
    """Discover every built-in node class via the registry's AST scan,
    then import each module so we have the actual class object the lint
    can introspect.

    The registry deliberately does not import node modules during scan
    (so a syntax error in one file does not bring down node discovery),
    so we import them here on demand. Test-collection time is dominated
    by the imports rather than the AST scan itself.
    """
    registry = NodeRegistry()
    errors = registry.scan_builtin(BUILTIN_NODES_DIR)
    if errors:
        pytest.fail(
            "Node registry reported scan errors: "
            + ", ".join(str(e) for e in errors)
        )
    classes: list[type] = []
    for entry in registry.nodes.values():
        module = importlib.import_module(entry.module)
        cls = getattr(module, entry.class_name)
        classes.append(cls)
    return classes


_NODE_CLASSES: list[type] = _all_node_classes()
_IDS: list[str] = [c.__name__ for c in _NODE_CLASSES]


def test_at_least_one_node_was_discovered() -> None:
    """Guard against the parametrised tests below silently degenerating
    into zero-iteration no-ops if the registry stops finding nodes."""
    assert _NODE_CLASSES, "expected at least one built-in node class"


@pytest.mark.parametrize("cls", _NODE_CLASSES, ids=_IDS)
def test_describe_node_smoke(cls: type) -> None:
    """``describe_node`` succeeds on every registered node class.

    Not xfail-marked: the introspection helper must work on every node
    today, otherwise the AI flow assistant's catalog renderer would
    crash partway through. If a new node breaks this it needs to be
    fixed (typically by giving its constructor sensible defaults).
    """
    out = describe_node(cls)
    assert out["class_name"] == cls.__name__
    assert "inputs" in out
    assert "outputs" in out
    assert "params" in out


@pytest.mark.xfail(
    reason="docstring sweep pending — issue #187",
    strict=False,
)
@pytest.mark.parametrize("cls", _NODE_CLASSES, ids=_IDS)
def test_node_has_meaningful_docstring(cls: type) -> None:
    """Every node class has a docstring of at least a sentence or two.

    Threshold of 30 characters catches single-word docstrings without
    forcing busywork on already-documented nodes.
    """
    doc = (cls.__doc__ or "").strip()
    assert len(doc) >= 30, (
        f"{cls.__name__}: docstring missing or too short "
        f"(have {len(doc)} chars, want >= 30)"
    )


@pytest.mark.xfail(
    reason="port-description sweep pending — issue #187",
    strict=False,
)
@pytest.mark.parametrize("cls", _NODE_CLASSES, ids=_IDS)
def test_param_ports_have_description(cls: type) -> None:
    """Every editable parameter — both port-style ``param_input_ports``
    and constant ``params`` — carries a ``"description"`` in its
    metadata.

    Image-flow input ports (no ``"param_type"`` in metadata) are exempt:
    their semantics are conveyed by ``accepted_types``, and a per-port
    description on every image input would be repetitive without adding
    information. Constant params and inline-editable params, by
    contrast, control behaviour the user has to understand.
    """
    inst = cls()
    missing: list[str] = []
    for port in inst.param_input_ports:
        if not port.metadata.get("description"):
            missing.append(f"input '{port.name}'")
    for param in inst.params:
        if not param.metadata.get("description"):
            missing.append(f"param '{param.name}'")
    assert not missing, (
        f"{cls.__name__}: parameter(s) without 'description' metadata: "
        f"{missing}"
    )


@pytest.mark.xfail(
    reason="enum-mapping sweep pending — issue #187",
    strict=False,
)
@pytest.mark.parametrize("cls", _NODE_CLASSES, ids=_IDS)
def test_enum_params_have_mapping(cls: type) -> None:
    """Every ENUM-typed parameter declares an ``"enum"`` mapping in its
    metadata.

    Without the mapping, the AI flow assistant cannot know that
    ``Dither.method=6`` means *Floyd-Steinberg*; consumers fall back to
    raw integers and produce broken graphs. Both encoding styles
    (Python :class:`Enum` subclass or literal ``dict[int, str]``) are
    accepted — :func:`core.node_doc._normalize_enum` collapses them.
    """
    inst = cls()
    missing: list[str] = []
    for port in inst.param_input_ports:
        if port.metadata.get("param_type") == NodeParamType.ENUM:
            if "enum" not in port.metadata:
                missing.append(f"input '{port.name}'")
    for param in inst.params:
        if param.metadata.get("param_type") == NodeParamType.ENUM:
            if "enum" not in param.metadata:
                missing.append(f"param '{param.name}'")
    assert not missing, (
        f"{cls.__name__}: ENUM parameter(s) without 'enum' metadata: "
        f"{missing}"
    )

"""Structured-introspection helpers for node documentation.

This module is the single source of truth for the metadata schema that
every node's :class:`~core.port.InputPort` and :class:`~core.node_base.NodeParam`
populate via the ``metadata=`` constructor argument, and it provides the
introspection helpers that turn a node class into a machine-readable
description.

Two consumers are intended:

* **Parameter-panel tooltips and inline help in the editor** — the same
  description text that documents a port for a human user is what shows
  up on hover.
* **The AI flow assistant** (issue #187) — the catalog of node
  descriptions feeds the LLM's system prompt so generated graphs only
  ever reference real nodes, real ports, and valid parameter values.

Keeping both consumers downstream of a single schema avoids the
parameter-panel tooltips and the assistant catalog drifting apart.

Schema status
-------------

The schema is permissive on purpose: every key is optional, and most
existing nodes today populate only a subset (typically ``param_type`` and
``default``). The companion lint test in
``tests/test_node_documentation.py`` is currently marked ``xfail`` so it
documents the target without breaking CI; an upcoming sweep fills in the
missing ``description`` / ``min`` / ``max`` / ``enum`` keys node by node,
and the final sweep PR removes the ``xfail`` markers.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, TypedDict

from core.node_base import NodeBase, NodeParam, NodeParamType
from core.port import InputPort, OutputPort


class PortMetadata(TypedDict, total=False):
    """Recognized keys in :attr:`InputPort.metadata` / :attr:`NodeParam.metadata`.

    All keys are optional. The TypedDict serves as the canonical list of
    keys the UI and the assistant know about; any other keys are ignored
    by the introspection helpers but are not rejected (nodes are free to
    stash backend-specific hints under unique names).
    """

    #: Inline-editor type hint. When present, the UI renders an inline
    #: widget on the port row instead of a plain socket.
    param_type: NodeParamType

    #: Literal default value used when the port has no upstream
    #: connection. Mirrored from :attr:`InputPort.default_value` /
    #: :attr:`NodeParam.default_value` for the widget's convenience.
    default: Any

    #: Human-readable explanation of what this port controls. One or two
    #: sentences. Surfaces as a tooltip in the editor and as the port's
    #: description in the assistant's node catalog.
    description: str

    #: Inclusive lower bound for numeric ports. Drives spinner / slider
    #: range and the assistant's value validation.
    min: float

    #: Inclusive upper bound for numeric ports. Same role as :data:`min`.
    max: float

    #: Step size for numeric editors (1 for INT, smaller for FLOAT).
    step: float

    #: Display unit string for numeric ports — e.g. ``"px"``, ``"deg"``,
    #: ``"ms"``. Purely informational, shown next to the value in the UI.
    unit: str

    #: Mapping from integer value to display label, or a Python
    #: :class:`Enum` subclass that defines the same. Required for
    #: :attr:`NodeParamType.ENUM` ports — without it a consumer cannot
    #: render or validate the value. :func:`describe_port` normalises
    #: both encodings to ``dict[int, str]`` so consumers always see the
    #: dict form.
    enum: Any

    #: File-dialog filter string for :attr:`NodeParamType.FILE_PATH` /
    #: :attr:`NodeParamType.FOLDER` ports — e.g. ``"Images (*.png *.jpg)"``.
    filter: str

    #: Anchor directory used to resolve relative paths in
    #: :attr:`NodeParamType.FILE_PATH` / :attr:`NodeParamType.FOLDER`
    #: ports. Typically :data:`constants.INPUT_DIR` or
    #: :data:`constants.OUTPUT_DIR`.
    base_dir: Any

    #: ``"save"`` or ``"open"`` for :attr:`NodeParamType.FILE_PATH`
    #: ports. Decides whether the file dialog is a save dialog (with an
    #: overwrite prompt) or an open dialog.
    mode: str


def _normalize_enum(value: Any) -> dict[int, str]:
    """Convert either an :class:`Enum` subclass or a literal mapping
    into ``dict[int, str]``.

    Both encodings are used in the existing nodes today
    (``metadata={"enum": ResizeMethod}`` vs.
    ``metadata={"enum": {0: "Off", 1: "On"}}``), so consumers should not
    have to special-case which one they got.
    """
    if isinstance(value, type) and issubclass(value, Enum):
        out: dict[int, str] = {}
        for member in value:
            raw = member.value
            if isinstance(raw, tuple):
                raw = raw[0]
            try:
                out[int(raw)] = member.name
            except (TypeError, ValueError):
                out[len(out)] = member.name
        return out
    if isinstance(value, dict):
        return {int(k): str(v) for k, v in value.items()}
    raise TypeError(
        f"unsupported enum metadata: {type(value).__name__} "
        f"(expected Enum subclass or dict[int, str])"
    )


def _describe_metadata(metadata: dict) -> dict:
    """Extract the recognised :class:`PortMetadata` keys from a raw
    ``metadata`` dict, normalising :data:`PortMetadata.enum` to dict
    form. Unknown keys are dropped — the schema is the contract."""
    out: dict = {}
    pt = metadata.get("param_type")
    if isinstance(pt, NodeParamType):
        out["param_type"] = pt.name
    for key in ("description", "min", "max", "step", "unit", "filter", "mode"):
        if key in metadata:
            out[key] = metadata[key]
    if "enum" in metadata:
        out["enum"] = _normalize_enum(metadata["enum"])
    return out


def describe_port(port: InputPort) -> dict:
    """Return a JSON-serialisable description of an :class:`InputPort`.

    Output schema (every key always present unless noted):

    * ``name``           — port name (str)
    * ``accepted_types`` — sorted list of :class:`IoDataType` names
    * ``optional``       — bool
    * ``default``        — present iff the port has a default value
    * ``param_type``     — present iff inline-editable
    * ``description``    — present iff the node author supplied one
    * ``min`` / ``max`` / ``step`` / ``unit`` / ``enum`` / ``filter`` /
      ``mode`` — present iff the node author supplied them
    """
    out: dict = {
        "name":           port.name,
        "accepted_types": sorted(t.name for t in port.accepted_types),
        "optional":       port.optional,
    }
    if port.has_default:
        out["default"] = port.default_value
    out.update(_describe_metadata(port.metadata))
    return out


def describe_param(param: NodeParam) -> dict:
    """Return a JSON-serialisable description of a constant
    :class:`NodeParam` (the inline non-port-driven config widgets used
    by sources, sinks, and a handful of filters).

    Output schema mirrors :func:`describe_port` minus the port-only
    fields (``accepted_types``, ``optional``)."""
    out: dict = {
        "name":    param.name,
        "default": param.default_value,
    }
    out.update(_describe_metadata(param.metadata))
    return out


def describe_output(port: OutputPort) -> dict:
    """Return a JSON-serialisable description of an :class:`OutputPort`."""
    return {
        "name":  port.name,
        "emits": sorted(t.name for t in port.emits),
    }


def describe_node(cls: type[NodeBase]) -> dict:
    """Return a JSON-serialisable description of a node class.

    Instantiates ``cls`` with no arguments to read its actual port and
    param structure — every concrete node in the codebase honours the
    no-arg constructor convention. The output is intended for the
    parameter-panel tooltips and for the AI flow assistant's catalog
    (issue #187), so the schema is kept stable.
    """
    inst = cls()
    return {
        "class_name":   cls.__name__,
        "display_name": inst.display_name,
        "section":      inst.section,
        "module":       cls.__module__,
        "docstring":    (cls.__doc__ or "").strip(),
        "inputs":       [describe_port(p) for p in inst.inputs],
        "outputs":      [describe_output(p) for p in inst.outputs],
        "params":       [describe_param(p) for p in inst.params],
    }

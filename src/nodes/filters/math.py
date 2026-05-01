from __future__ import annotations

import ast
import math as _math
from typing import Any, Final

import numpy as np
from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase, NodeParamType
from core.params import StringParam
from core.port import InputPort, OutputPort


# AST node types accepted inside a Math expression. Anything else is
# rejected at compile time. The set is deliberately *small* — every
# entry was added because a user-typed expression genuinely needs it,
# not because Python's grammar allows it. Notable omissions, all of
# which are common sandbox-escape primitives:
#
#   ast.Attribute      — ``A.__class__`` etc., the classic escape
#   ast.Lambda         — ``lambda: A``
#   ast.NamedExpr      — ``x := A`` (Python 3.8+ walrus)
#   ast.JoinedStr      — f-strings (allow nested expression parsing)
#   ast.FormattedValue — f-string field
#   ast.Starred        — ``*args`` / ``**kwargs`` in calls
#   ast.keyword        — ``f(a=1)`` (we only allow positional args)
#   ast.GeneratorExp / ListComp / SetComp / DictComp
#   ast.List / Tuple / Set / Dict
#   ast.Yield / YieldFrom / Await
#   ast.MatMult / BitAnd / BitOr / BitXor / LShift / RShift / Invert
#   ast.Is / IsNot / In / NotIn (identity / membership)
#
# ``ast.Subscript`` is allowed *only* in the narrow form ``v[<int>]``
# (validated below) so the user can write ``v[1] + v[2]`` against the
# fixed pool of input ports. Every other subscript shape is rejected.
_ALLOWED_AST_NODES: Final[frozenset[type[ast.AST]]] = frozenset({
    ast.Expression,
    ast.BinOp, ast.UnaryOp,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.USub, ast.UAdd,
    ast.IfExp,                          # ternary `a if cond else b`
    ast.Compare,
    ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq, ast.NotEq,
    ast.BoolOp, ast.And, ast.Or, ast.Not,
    ast.Call, ast.Load,
    ast.Constant, ast.Name,
    ast.Subscript,
})


# Allowed Constant payload types. ``ast.Constant`` is normally produced
# by the parser only for literal numbers, strings, None, True / False,
# bytes and Ellipsis. Strings and bytes are inert under our other
# restrictions (no attribute access, no method calls), but numeric
# expressions have no use for them either way — disallow to keep the
# threat model boring. Bool is allowed because a literal ``True`` /
# ``False`` is sometimes useful as a 0 / 1 multiplier. ``None`` is
# rejected so an expression that accidentally returns ``None`` fails
# at parse time rather than producing a non-numeric scalar downstream.
_ALLOWED_CONSTANT_TYPES: Final[tuple[type, ...]] = (int, float, complex, bool)


# Names callable from inside an expression. The values are numpy
# ufuncs / functions, so they accept Python and numpy scalars uniformly
# (the framework unwraps SCALAR ports to Python scalars before
# ``process_impl`` runs, but a user might also feed a numpy 0-d array
# in via a literal). ``min`` / ``max`` map to the elementwise variants
# so they take exactly two args and don't shadow Python's variadic
# builtin (which our restricted globals don't expose anyway).
_ALLOWED_FUNCTIONS: Final[dict[str, Any]] = {
    "sin":   np.sin,    "cos":   np.cos,   "tan":   np.tan,
    "asin":  np.arcsin, "acos":  np.arccos, "atan": np.arctan,
    "atan2": np.arctan2,
    "sinh":  np.sinh,   "cosh":  np.cosh,  "tanh":  np.tanh,
    "sqrt":  np.sqrt,   "exp":   np.exp,
    "log":   np.log,    "log2":  np.log2,  "log10": np.log10,
    "abs":   np.abs,
    "floor": np.floor,  "ceil":  np.ceil,  "round": np.round,
    "min":   np.minimum, "max":  np.maximum,
    "deg":   np.degrees, "rad":  np.radians,
}


_ALLOWED_CONSTANTS: Final[dict[str, float]] = {
    "pi": _math.pi,
    "e":  _math.e,
}


#: Total number of ``v[i]`` input ports the node owns. Slots past the
#: last connected one stay hidden in the editor (see
#: :attr:`NodeBase.SHOW_ONLY_USED_INPUTS`); the backend always carries
#: the full pool so connection indices stay stable across save / load.
_NUM_INPUTS: int = 9


def _validate_ast(tree: ast.AST) -> None:
    """Walk *tree* and reject anything not on the strict whitelist.

    Five classes of check, all enforced uniformly via :func:`ast.walk`
    so a deeply-nested escape attempt cannot hide behind a permissive
    parent node:

    1. Every visited node's *type* must appear in
       :data:`_ALLOWED_AST_NODES`. Primary defense — rejects
       ``Attribute``, ``Lambda``, ``Starred``, f-strings,
       comprehensions, walrus, etc.
    2. Every :class:`ast.Name` must reference an allowed function or
       constant — the *single* variable name ``v`` is also accepted
       there but only so the subscript form ``v[i]`` parses; a bare
       ``v`` reference outside a subscript is rejected at the parent
       :class:`ast.Subscript` check.
    3. Every :class:`ast.Call` must have a bare ``ast.Name`` as its
       callable, and that name must be in :data:`_ALLOWED_FUNCTIONS`
       (so ``pi(A)`` and ``(sin if A else cos)(B)`` both fail).
       Keyword arguments are explicitly rejected.
    4. Every :class:`ast.Constant`'s *value* must be one of
       :data:`_ALLOWED_CONSTANT_TYPES`. Strings, bytes, ``None`` and
       ``Ellipsis`` are rejected.
    5. Every :class:`ast.Subscript` must be of the exact shape
       ``Subscript(value=Name('v'), slice=Constant(positive int))``.
       Slices, attribute subscript values, computed indices and
       non-``v`` subscript targets all fail here.

    A bare ``v`` (no subscript) makes it through the AST whitelist
    but raises a :class:`TypeError` at eval time when an arithmetic
    op tries to consume the :class:`_OneIndexedView` proxy. Cleaner
    rejection is enforced via the parent-tracking pass below.
    """
    # First pass: type / name / call / constant / subscript shape.
    for node in ast.walk(tree):
        node_type = type(node)
        if node_type not in _ALLOWED_AST_NODES:
            raise ValueError(
                f"disallowed expression element: {node_type.__name__}"
            )
        if isinstance(node, ast.Name):
            if node.id not in _ALLOWED_NAMES:
                raise ValueError(f"unknown name in expression: {node.id!r}")
        elif isinstance(node, ast.Call):
            if not (
                isinstance(node.func, ast.Name)
                and node.func.id in _ALLOWED_FUNCTIONS
            ):
                raise ValueError(
                    "only bare top-level calls to whitelisted "
                    "functions are allowed"
                )
            if node.keywords:
                raise ValueError("keyword arguments are not allowed")
        elif isinstance(node, ast.Constant):
            if type(node.value) not in _ALLOWED_CONSTANT_TYPES:
                raise ValueError(
                    f"disallowed constant type: {type(node.value).__name__}"
                )
        elif isinstance(node, ast.Subscript):
            _validate_subscript(node)

    # Second pass: every reference to ``v`` must sit inside a
    # ``Subscript`` value. Catches bare ``v`` / ``v + 1`` /
    # ``sin(v)`` at parse time so the user gets a tidy error rather
    # than a runtime TypeError on the proxy object.
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            if not (isinstance(child, ast.Name) and child.id == _VARIABLE_NAME):
                continue
            if isinstance(parent, ast.Subscript) and parent.value is child:
                continue
            raise ValueError(
                f"{_VARIABLE_NAME!r} can only appear as a subscript "
                f"(e.g. v[1], v[2]); bare {_VARIABLE_NAME!r} is not allowed"
            )


def _validate_subscript(node: ast.Subscript) -> None:
    """Reject every subscript shape except ``v[<positive int literal>]``."""
    if not (isinstance(node.value, ast.Name) and node.value.id == _VARIABLE_NAME):
        raise ValueError(
            f"only {_VARIABLE_NAME!r} may be subscripted in an expression"
        )
    index_node = node.slice
    if not (isinstance(index_node, ast.Constant) and type(index_node.value) is int):
        raise ValueError(
            f"{_VARIABLE_NAME}[…] index must be a positive integer literal"
        )
    if index_node.value < 1:
        raise ValueError(
            f"{_VARIABLE_NAME}[…] index must be >= 1 (got {index_node.value})"
        )
    if index_node.value > _NUM_INPUTS:
        raise ValueError(
            f"{_VARIABLE_NAME}[{index_node.value}] is out of range "
            f"(node has v[1]..v[{_NUM_INPUTS}])"
        )


#: The single variable name an expression may reference. The user
#: subscripts it as ``v[1]``, ``v[2]``, etc. — one slot per input
#: port. Bare ``v`` references are rejected by :func:`_validate_ast`.
_VARIABLE_NAME: Final[str] = "v"


# Pre-computed once: the union of every name a parsed Name node may
# reference. Recomputing per validate() would re-allocate this same
# set on every keystroke in the editor.
_ALLOWED_NAMES: Final[frozenset[str]] = frozenset(
    {_VARIABLE_NAME}
    | _ALLOWED_FUNCTIONS.keys()
    | _ALLOWED_CONSTANTS.keys()
)


def _compile_expression(text: str):
    """Parse, validate and compile an expression string.

    Raises :class:`ValueError` on syntax errors or whitelist violations;
    returns the compiled bytecode object on success.
    """
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"invalid expression syntax: {exc.msg}") from exc
    _validate_ast(tree)
    return compile(tree, "<math-expr>", "eval")


class _ExpressionParam(StringParam):
    """StringParam that compiles the expression on every set.

    The validated bytecode is stashed on the owning instance under
    ``_compiled`` so :meth:`Math.process_impl` can call ``eval()``
    without re-parsing per frame. ``__set__`` is overridden in one
    place rather than spread across coerce / validate hooks because
    the compile result is needed *and* the original-text storage
    needs to land atomically — both written together so a bad
    expression leaves the previous valid one in place.
    """

    def __set__(self, instance: object, value: object) -> None:
        text = str(value).strip()
        if not text:
            raise ValueError(f"{self.name} must not be empty")
        compiled = _compile_expression(text)
        # Atomic adoption: only commit once compile + validation succeed.
        object.__setattr__(instance, self._private, text)
        object.__setattr__(instance, "_compiled", compiled)


class _OneIndexedView:
    """Read-only 1-indexed view onto a list of port values.

    The user references inputs as ``v[1]`` … ``v[N]`` to match the
    port labels (``v[1]`` is the first input). Internally the list is
    0-indexed, so this thin wrapper subtracts 1 on every read and
    raises a clear error for out-of-range or non-integer keys rather
    than letting :class:`IndexError` from the underlying list bubble
    up unannotated.
    """

    __slots__ = ("_values",)

    def __init__(self, values: list[float]) -> None:
        self._values = values

    def __getitem__(self, index: object) -> float:
        if not isinstance(index, int) or isinstance(index, bool):
            raise TypeError(
                f"v[…] index must be an integer (got {type(index).__name__})"
            )
        if index < 1 or index > len(self._values):
            raise IndexError(
                f"v[{index}] is out of range (have v[1]..v[{len(self._values)}])"
            )
        return self._values[index - 1]


class Math(NodeBase):
    """Evaluate an arithmetic expression on up to nine SCALAR streams.

    The node has nine optional ``v[i]`` SCALAR inputs. The editor
    starts with a single visible row and grows by one row each time
    the user wires up the previous tail (see
    :attr:`NodeBase.SHOW_ONLY_USED_INPUTS`). Unconnected ports use
    the inline-edited default of the corresponding row.

    ``expression`` is a Python-style arithmetic expression in
    ``v[1]`` … ``v[9]`` plus the constants ``pi`` / ``e`` and the
    whitelisted math helpers. A bad expression raises immediately on
    edit.

    Examples::

        "v[1] + v[2]"
        "v[1] * v[2] + v[3] * v[4]"
        "sin(v[1] * pi/180) * v[2]"
        "v[1] if v[2] > 0 else v[3]"
    """

    SHOW_ONLY_USED_INPUTS: bool = True

    expression = _ExpressionParam(
        "v[1]",
        constant=True,
        description=(
            "Arithmetic expression over the inputs v[1]..v[9] plus "
            "the helpers sin / cos / tan / asin / acos / atan / "
            "atan2 / sinh / cosh / tanh / sqrt / exp / log / log2 / "
            "log10 / abs / floor / ceil / round / min / max / deg / "
            "rad and the constants pi and e. Examples: 'v[1] + v[2]', "
            "'v[1] * v[2] + v[3] * v[4]', 'sin(v[1] * pi/180) * v[2]', "
            "'v[1] if v[2] > 0 else v[3]'."
        ),
    )

    def __init__(self) -> None:
        super().__init__("Math", section="Math")
        self._add_output(OutputPort("result", {IoDataType.SCALAR}))
        # Nine SCALAR inputs with FLOAT param-style metadata so the
        # UI renders an inline slider on every visible row. Default
        # 0.0 lets the expression evaluate against unconnected ports
        # without explicit user input.
        for i in range(1, _NUM_INPUTS + 1):
            self._add_input(InputPort(
                f"v[{i}]", {IoDataType.SCALAR},
                optional=True, default_value=0.0,
                metadata={
                    "param_type": NodeParamType.FLOAT,
                    "default": 0.0,
                },
            ))
        self._apply_default_params()

    @override
    def process_impl(self) -> None:
        # Build the value vector in port order. Connected ports
        # contribute their fresh payload; unconnected ports fall back
        # to the inline-edited default (the slider value).
        values: list[float] = []
        for port in self.inputs:
            if port.has_data:
                payload = port.data.payload
                values.append(float(
                    payload.item() if hasattr(payload, "item") else payload
                ))
            else:
                default = port.default_value
                values.append(float(default) if default is not None else 0.0)
        namespace: dict[str, Any] = {
            "v": _OneIndexedView(values),
            **_ALLOWED_CONSTANTS,
            **_ALLOWED_FUNCTIONS,
        }
        result = eval(  # noqa: S307 — validated AST + empty builtins.
            self._compiled,
            {"__builtins__": {}},
            namespace,
        )
        self.outputs[0].send(IoData.from_scalar(result))

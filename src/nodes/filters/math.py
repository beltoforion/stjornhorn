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
#   ast.Subscript      — ``v[__class__]`` and friends; we don't need
#                        indexing because every input has its own name
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


#: Total number of ``v_i`` input ports the node owns. Slots past the
#: last connected one stay hidden in the editor (see
#: :attr:`NodeBase.SHOW_ONLY_USED_INPUTS`); the backend always carries
#: the full pool so connection indices stay stable across save / load.
_NUM_INPUTS: int = 9


#: Names of the input ports, in port order. Each name is a valid
#: Python identifier so the expression parser can reference it as a
#: bare :class:`ast.Name` and the framework's existing
#: ``setattr(node, port.name, value)`` plumbing (inline widgets,
#: save / load) works without any special-casing.
_INPUT_NAMES: Final[tuple[str, ...]] = tuple(
    f"v_{i}" for i in range(1, _NUM_INPUTS + 1)
)


def _validate_ast(tree: ast.AST) -> None:
    """Walk *tree* and reject anything not on the strict whitelist.

    Four classes of check, all enforced uniformly via :func:`ast.walk`
    so a deeply-nested escape attempt cannot hide behind a permissive
    parent node:

    1. Every visited node's *type* must appear in
       :data:`_ALLOWED_AST_NODES`. Primary defense — rejects
       ``Attribute``, ``Subscript``, ``Lambda``, ``Starred``,
       f-strings, comprehensions, walrus, etc.
    2. Every :class:`ast.Name` must reference an input port
       (``v_1`` … ``v_9``), an allowed function, or an allowed
       constant — anything else is rejected.
    3. Every :class:`ast.Call` must have a bare ``ast.Name`` as its
       callable, and that name must be in :data:`_ALLOWED_FUNCTIONS`
       (so ``pi(A)`` and ``(sin if A else cos)(B)`` both fail).
       Keyword arguments are explicitly rejected.
    4. Every :class:`ast.Constant`'s *value* must be one of
       :data:`_ALLOWED_CONSTANT_TYPES`. Strings, bytes, ``None`` and
       ``Ellipsis`` are rejected.
    """
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


# Pre-computed once: the union of every name a parsed Name node may
# reference. Recomputing per validate() would re-allocate this same
# set on every keystroke in the editor.
_ALLOWED_NAMES: Final[frozenset[str]] = frozenset(
    set(_INPUT_NAMES)
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


class Math(NodeBase):
    """Evaluate an arithmetic expression on up to nine SCALAR streams.

    The node has nine optional ``v_i`` SCALAR inputs. The editor
    starts with a single visible row and grows by one row each time
    the user wires up the previous tail (see
    :attr:`NodeBase.SHOW_ONLY_USED_INPUTS`). Unconnected ports use
    the inline-edited default of the corresponding row.

    ``expression`` is a Python-style arithmetic expression in
    ``v_1`` … ``v_9`` plus the constants ``pi`` / ``e`` and the
    whitelisted math helpers. A bad expression raises immediately on
    edit.

    Examples::

        "v_1 + v_2"
        "v_1 * v_2 + v_3 * v_4"
        "sin(v_1 * pi/180) * v_2"
        "v_1 if v_2 > 0 else v_3"
    """

    SHOW_ONLY_USED_INPUTS: bool = True

    expression = _ExpressionParam(
        "v_1",
        constant=True,
        description=(
            "Arithmetic expression over the inputs v_1..v_9 plus "
            "the helpers sin / cos / tan / asin / acos / atan / "
            "atan2 / sinh / cosh / tanh / sqrt / exp / log / log2 / "
            "log10 / abs / floor / ceil / round / min / max / deg / "
            "rad and the constants pi and e. Examples: 'v_1 + v_2', "
            "'v_1 * v_2 + v_3 * v_4', 'sin(v_1 * pi/180) * v_2', "
            "'v_1 if v_2 > 0 else v_3'."
        ),
    )

    def __init__(self) -> None:
        super().__init__("Math", section="Math")
        self._add_output(OutputPort("result", {IoDataType.SCALAR}))
        # Nine SCALAR inputs with FLOAT param-style metadata so the
        # UI renders an inline slider on every visible row. Default
        # 0.0 lets the expression evaluate against unconnected ports
        # without explicit user input.
        for name in _INPUT_NAMES:
            self._add_input(InputPort(
                name, {IoDataType.SCALAR},
                optional=True, default_value=0.0,
                metadata={
                    "param_type": NodeParamType.FLOAT,
                    "default": 0.0,
                },
            ))
        self._apply_default_params()

    @override
    def process_impl(self) -> None:
        # Build the eval namespace. Connected ports contribute their
        # fresh payload; unconnected ports fall back to the
        # inline-edited slider value (``setattr`` from the inline
        # widget lands on ``node.v_i`` directly since these ports
        # have no descriptor) or the port's default if the slider
        # was never touched.
        namespace: dict[str, Any] = {
            **_ALLOWED_CONSTANTS,
            **_ALLOWED_FUNCTIONS,
        }
        for port in self.inputs:
            if port.has_data:
                payload = port.data.payload
                value = float(
                    payload.item() if hasattr(payload, "item") else payload
                )
            else:
                stored = getattr(self, port.name, port.default_value)
                value = float(stored) if stored is not None else 0.0
            namespace[port.name] = value
        result = eval(  # noqa: S307 — validated AST + empty builtins.
            self._compiled,
            {"__builtins__": {}},
            namespace,
        )
        self.outputs[0].send(IoData.from_scalar(result))

from __future__ import annotations

import ast
import math as _math
from typing import Any, Final

import numpy as np
from typing_extensions import override

from core.io_data import IoData, IoDataType
from core.node_base import NodeBase, NodeParam, NodeParamType
from core.port import InputPort, OutputPort


# AST node types accepted inside a Math expression. Anything else is
# rejected at compile time. The set is deliberately *small* — every
# entry was added because a user-typed expression genuinely needs it,
# not because Python's grammar allows it. Notable omissions, all of
# which are common sandbox-escape primitives:
#
#   ast.Attribute      — ``A.__class__`` etc., the classic escape
#   ast.Subscript      — ``A[0]`` (lets you reach into containers)
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
# Concretely: no attribute access, no item access, no statements, no
# anonymous functions, no comprehensions, no string interpolation, no
# argument unpacking, no keyword args, no bitwise / matmul ops, no
# identity / membership comparisons.
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
# restrictions (no attribute access, no subscript, no method calls), but
# numeric expressions have no use for them either way — disallow to
# keep the threat model boring. Bool is allowed because a literal
# ``True`` / ``False`` is sometimes useful as a 0 / 1 multiplier.
# ``None`` is rejected so an expression that accidentally returns
# ``None`` fails at parse time rather than producing a non-numeric
# scalar downstream.
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


_VARIABLE_NAMES: Final[frozenset[str]] = frozenset({"a", "b", "c", "d"})


# Pre-computed once: the union of every name a parsed Name node may
# reference. Recomputing per validate() would re-allocate this same
# set on every keystroke in the editor.
_ALLOWED_NAMES: Final[frozenset[str]] = frozenset(
    _VARIABLE_NAMES
    | _ALLOWED_FUNCTIONS.keys()
    | _ALLOWED_CONSTANTS.keys()
)


class Math(NodeBase):
    """Evaluate an arithmetic expression on up to four SCALAR streams.

    Inputs:
      ``a`` (required) — fires the node on every new value.
      ``b``, ``c``, ``d`` (optional, default 0.0) — feed the
      matching variable in the expression. Unconnected ports keep
      their inline-edited default.

    Param:
      ``expression`` — a Python-style arithmetic expression in the
      lowercase variables ``a``, ``b``, ``c``, ``d`` (matching the
      input port names) plus the helpers in
      :data:`_ALLOWED_FUNCTIONS` and the constants ``pi`` / ``e``.
      Default ``"a"``.

    Examples:
      ``"a + b"``                  — classic binary add.
      ``"a * b + c * d"``          — bilinear blend.
      ``"sin(a * pi/180) * b"``    — a in degrees, scaled by b.
      ``"a if b > 0 else c"``      — conditional select.

    Safety:
      The expression is parsed via :mod:`ast` and every visited node
      is checked against :data:`_ALLOWED_AST_NODES`,
      :data:`_ALLOWED_NAMES`, :data:`_ALLOWED_CONSTANT_TYPES` and
      (for calls) :data:`_ALLOWED_FUNCTIONS`. Compilation happens
      after validation; the per-frame ``eval`` runs with empty
      ``__builtins__`` and a fixed namespace. There is no path from a
      user-typed expression to attribute access, item access,
      statements, comprehensions, lambdas, f-strings, argument
      unpacking, keyword args, or any name that is not explicitly
      whitelisted — sandbox-escape patterns like
      ``().__class__.__bases__[0].__subclasses__()`` are rejected at
      parse time. A bad expression raises at the moment the
      ``expression`` param is set, so a typo surfaces immediately in
      the UI rather than mid-flow.
    """

    def __init__(self) -> None:
        super().__init__("Math", section="Math")
        self._a: float = 0.0
        self._b: float = 0.0
        self._c: float = 0.0
        self._d: float = 0.0
        self._expression: str = "a"
        # Compiled bytecode for the current expression, refreshed by
        # the :meth:`expression` setter. Stored separately so per-frame
        # evaluation skips the parse step.
        self._compiled = self._compile_expression(self._expression)

        self._add_input(InputPort("a", {IoDataType.SCALAR}))
        for name, default in (("b", 0.0), ("c", 0.0), ("d", 0.0)):
            self._add_input(InputPort(
                name,
                {IoDataType.SCALAR},
                optional=True,
                default_value=default,
                metadata={
                    "default": default,
                    "param_type": NodeParamType.FLOAT,
                    "description": (
                        f"Operand {name!r} in the expression. Unconnected "
                        "ports use the inline-edited default."
                    ),
                },
            ))

        self._add_param(NodeParam(
            "expression",
            NodeParamType.STRING,
            default="a",
            metadata={
                "description": (
                    "Arithmetic expression in the variables a, b, c, d "
                    "plus the helpers sin / cos / tan / asin / acos / "
                    "atan / atan2 / sinh / cosh / tanh / sqrt / exp / "
                    "log / log2 / log10 / abs / floor / ceil / round / "
                    "min / max / deg / rad and the constants pi and e. "
                    "Examples: 'a + b', 'a * b + c * d', "
                    "'sin(a * pi/180) * b', 'a if b > 0 else c'."
                ),
            },
        ))

        self._add_output(OutputPort("result", {IoDataType.SCALAR}))
        self._apply_default_params()

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def expression(self) -> str:
        return self._expression

    @expression.setter
    def expression(self, value: str) -> None:
        text = str(value).strip()
        if not text:
            raise ValueError("expression must not be empty")
        compiled = self._compile_expression(text)
        # Atomic adoption: only commit the new expression once compile
        # + validation succeed; on failure ``self._compiled`` keeps
        # evaluating the previous valid expression.
        self._expression = text
        self._compiled = compiled

    @property
    def a(self) -> float:
        return self._a

    @a.setter
    def a(self, value: object) -> None:
        self._a = float(value)

    @property
    def b(self) -> float:
        return self._b

    @b.setter
    def b(self, value: object) -> None:
        self._b = float(value)

    @property
    def c(self) -> float:
        return self._c

    @c.setter
    def c(self, value: object) -> None:
        self._c = float(value)

    @property
    def d(self) -> float:
        return self._d

    @d.setter
    def d(self, value: object) -> None:
        self._d = float(value)

    # ── NodeBase interface ─────────────────────────────────────────────────────

    @override
    def process_impl(self) -> None:
        # NodeBase populated self._a / _b / _c / _d from connected
        # input ports before this call (port-driven attribute machinery
        # in :meth:`NodeBase._populate_port_driven_attributes`).
        # Unconnected optional ports keep the attribute's current
        # value (the inline-edited default).
        namespace: dict[str, Any] = {
            "a": self._a, "b": self._b, "c": self._c, "d": self._d,
            **_ALLOWED_CONSTANTS,
            **_ALLOWED_FUNCTIONS,
        }
        result = eval(  # noqa: S307 — validated AST + empty builtins.
            self._compiled,
            {"__builtins__": {}},
            namespace,
        )
        self.outputs[0].send(IoData.from_scalar(result))

    # ── Internals ──────────────────────────────────────────────────────────────

    @staticmethod
    def _compile_expression(text: str):
        try:
            tree = ast.parse(text, mode="eval")
        except SyntaxError as exc:
            raise ValueError(f"invalid expression syntax: {exc.msg}") from exc
        Math._validate_ast(tree)
        return compile(tree, "<math-expr>", "eval")

    @staticmethod
    def _validate_ast(tree: ast.AST) -> None:
        """Walk *tree* and reject anything not on the strict whitelist.

        Four classes of check, all enforced uniformly via
        :func:`ast.walk` so a deeply-nested escape attempt cannot hide
        behind a permissive parent node:

        1. Every visited node's *type* must appear in
           :data:`_ALLOWED_AST_NODES`. This is the primary defense —
           it rejects ``Attribute``, ``Subscript``, ``Lambda``,
           ``Starred``, f-strings, comprehensions, walrus, etc.
        2. Every :class:`ast.Name` must reference one of the four
           variables, an allowed function or an allowed constant.
        3. Every :class:`ast.Call` must have a bare ``ast.Name`` as
           its callable, and that name must be in
           :data:`_ALLOWED_FUNCTIONS` (so ``pi(A)`` and
           ``(sin if A else cos)(B)`` both fail). Keyword arguments
           are explicitly rejected.
        4. Every :class:`ast.Constant`'s *value* must be one of
           :data:`_ALLOWED_CONSTANT_TYPES`. Strings, bytes, ``None``
           and ``Ellipsis`` are rejected — they have no use in an
           arithmetic expression and disallowing them keeps the
           threat surface boring.
        """
        for node in ast.walk(tree):
            node_type = type(node)
            if node_type not in _ALLOWED_AST_NODES:
                raise ValueError(
                    f"disallowed expression element: {node_type.__name__}"
                )
            if isinstance(node, ast.Name):
                if node.id not in _ALLOWED_NAMES:
                    raise ValueError(
                        f"unknown name in expression: {node.id!r}"
                    )
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

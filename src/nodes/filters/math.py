from __future__ import annotations

import ast
import math as _math
from typing import Any, Final

import numpy as np
from typing_extensions import override

from core.dynamic_ports import MAX_DYNAMIC_INPUTS, DynamicInputGroup
from core.io_data import IoData, IoDataType
from core.node_base import NodeBase, NodeParamType
from core.params import StringParam
from core.port import OutputPort


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
# dynamic input ports. Every other subscript shape is rejected.
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


#: The lone variable name an expression may reference. The user
#: subscripts it as ``v[1]``, ``v[2]``, etc. — one slot per dynamic
#: input port. ``v`` itself never resolves bare; an expression like
#: ``v + 1`` raises at validation time.
_VARIABLE_NAME: Final[str] = "v"


# Pre-computed once: the union of every name a parsed Name node may
# reference. Recomputing per validate() would re-allocate this same
# set on every keystroke in the editor.
_ALLOWED_NAMES: Final[frozenset[str]] = frozenset(
    {_VARIABLE_NAME}
    | _ALLOWED_FUNCTIONS.keys()
    | _ALLOWED_CONSTANTS.keys()
)


def _validate_ast(tree: ast.AST) -> None:
    """Walk *tree* and reject anything not on the strict whitelist.

    Five classes of check, all enforced uniformly via :func:`ast.walk`
    so a deeply-nested escape attempt cannot hide behind a permissive
    parent node:

    1. Every visited node's *type* must appear in
       :data:`_ALLOWED_AST_NODES`. This is the primary defense — it
       rejects ``Attribute``, ``Lambda``, ``Starred``, f-strings,
       comprehensions, walrus, etc.
    2. Every :class:`ast.Name` must reference :data:`_VARIABLE_NAME`,
       an allowed function or an allowed constant.
    3. Every :class:`ast.Call` must have a bare ``ast.Name`` as its
       callable, and that name must be in :data:`_ALLOWED_FUNCTIONS`
       (so ``pi(A)`` and ``(sin if A else cos)(B)`` both fail).
       Keyword arguments are explicitly rejected.
    4. Every :class:`ast.Constant`'s *value* must be one of
       :data:`_ALLOWED_CONSTANT_TYPES`. Strings, bytes, ``None`` and
       ``Ellipsis`` are rejected.
    5. Every :class:`ast.Subscript` must be of the exact shape
       ``Subscript(value=Name('v'), slice=Constant(int))`` with the
       index ``>= 1``. Slices, attribute subscript values, computed
       indices and bare ``v`` references all fail here.
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
        elif isinstance(node, ast.Subscript):
            _validate_subscript(node)


def _validate_subscript(node: ast.Subscript) -> None:
    """Reject every subscript shape except ``v[<positive int literal>]``.

    Split out so the four narrow checks (value is the bare ``v`` name,
    index is a literal, literal is an int, int is positive) all read
    in one place. Bare ``v`` references — ``v + 1``, ``sin(v)`` — are
    rejected indirectly: they trigger :class:`ast.Name` inside an
    arithmetic position and are still rejected at the function /
    operand boundary by Python's eval (no subscript means no value).
    """
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
    port labels (``v[1]`` is the first dynamic input). Internally the
    list is 0-indexed, so this thin wrapper subtracts 1 on every read
    and raises a clear error for out-of-range or non-integer keys
    rather than silently returning ``IndexError`` from the underlying
    list.
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


#: Stable key under which Math publishes its dynamic input group in
#: the saved-flow JSON. On-disk schema — do not rename.
_V_GROUP_KEY: str = "v"


class Math(NodeBase):
    """Evaluate an arithmetic expression on a list of SCALAR streams.

    The node starts with a single input ``v[1]``. Whenever the tail
    input is wired to an upstream, a fresh empty ``v[N+1]`` appears
    below it, up to a hard cap of nine. Unconnected inputs use the
    inline-edited default of the corresponding port row.

    ``expression`` is a Python-style arithmetic expression in
    ``v[1]`` … ``v[N]`` plus the constants ``pi`` / ``e`` and the
    whitelisted math helpers. A bad expression raises immediately on
    edit. The dispatcher fires once **at least one** connected input
    has fresh data; missing inputs that the expression doesn't
    reference are simply ignored.

    Examples::

        "v[1] + v[2]"
        "v[1] * v[2] + v[3] * v[4]"
        "sin(v[1] * pi/180) * v[2]"
        "v[1] if v[2] > 0 else v[3]"
    """

    expression = _ExpressionParam(
        "v[1]",
        constant=True,
        description=(
            "Arithmetic expression over the dynamic inputs v[1]..v[N] "
            "plus the helpers sin / cos / tan / asin / acos / atan / "
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
        # Dynamic SCALAR inputs. Metadata carries the FLOAT param hint
        # so the UI renders an inline slider on each row — Math's
        # ports double as both data inputs and inline-edited
        # constants when nothing's wired.
        self._v_group = DynamicInputGroup(
            self,
            name_template="v[{i}]",
            accepted_types={IoDataType.SCALAR},
            metadata={"param_type": NodeParamType.FLOAT, "default": 0.0},
            max_count=MAX_DYNAMIC_INPUTS,
        )
        # Seed each port's inline default to 0.0. New ports created
        # later by the dynamic group inherit this through their
        # metadata's ``default`` key when the UI builds a widget; the
        # framework's port machinery uses ``default_value`` directly.
        for port in self._v_group.ports:
            port.default_value = 0.0
        # Hook every existing and future port so a connect / disconnect
        # event seeds new ports with the same default. Future ports
        # are picked up via the ports-changed listener on the node.
        self.add_ports_changed_listener(self._seed_new_port_defaults)
        self._dynamic_input_groups: dict[str, DynamicInputGroup] = {
            _V_GROUP_KEY: self._v_group,
        }
        self._apply_default_params()

    def _seed_new_port_defaults(self) -> None:
        """Initialise ``default_value`` on freshly-appended dynamic ports.

        Idempotent: ports that already have a non-``None`` default are
        left alone, so a saved-flow restore (which writes the user's
        last value before this listener fires) wins over the seed.
        """
        for port in self._v_group.ports:
            if port.default_value is None:
                port.default_value = 0.0

    @override
    def process_impl(self) -> None:
        # Build the value vector in port order. Connected ports
        # contribute their fresh payload; unconnected ports fall back
        # to their inline-edited default (the slider value).
        values: list[float] = []
        for port in self._v_group.ports:
            if port.has_data:
                payload = port.data.payload
                values.append(float(payload.item() if hasattr(payload, "item") else payload))
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

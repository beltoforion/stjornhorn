"""Unit tests for the Math expression node.

Two themes:

* **Behaviour** — round-trip a handful of representative expressions
  through the node and verify the output. Covers operators, the
  whitelisted function set, ternary, default-zero on unconnected
  optional ports, and the streaming dispatcher contract.

* **Safety** — exhaustively reject sandbox-escape and out-of-scope
  syntax at *parse time*. The primary defense is the AST type
  whitelist; the cases below probe each excluded node type and a few
  classic escape primitives, so a regression that accidentally allows
  one (e.g. someone adding ``ast.Attribute`` "to support
  ``a.real``") fails this suite immediately.
"""
from __future__ import annotations

import math

import pytest

from core.io_data import IoData, IoDataType
from core.port import InputPort, OutputPort
from nodes.filters.math import Math


def _wire(node: Math, *, connect_optional: bool = False) -> tuple[
    OutputPort, OutputPort, OutputPort, OutputPort, list[IoData],
]:
    """Connect upstreams + a capturing sink and return them.

    Optional ``b`` / ``c`` / ``d`` ports stay unconnected unless
    ``connect_optional`` is ``True``. When connected, every value on
    every connected port must be sent before the dispatcher fires —
    a connected optional port counts as ``waited`` too.
    """
    up_a = OutputPort("a_up", {IoDataType.SCALAR})
    up_b = OutputPort("b_up", {IoDataType.SCALAR})
    up_c = OutputPort("c_up", {IoDataType.SCALAR})
    up_d = OutputPort("d_up", {IoDataType.SCALAR})
    up_a.connect(node.inputs[0])
    if connect_optional:
        up_b.connect(node.inputs[1])
        up_c.connect(node.inputs[2])
        up_d.connect(node.inputs[3])

    captured: list[IoData] = []
    sink = InputPort("sink", {IoDataType.SCALAR})
    sink.add_listener(
        lambda: captured.append(sink.data) if sink.has_data else None
    )
    node.outputs[0].connect(sink)
    return up_a, up_b, up_c, up_d, captured


# ── Defaults / single-input expressions ───────────────────────────────────────


def test_default_expression_passes_a_through() -> None:
    """A brand-new node has expression='a'; emitting on a should
    return a unchanged on every frame."""
    node = Math()
    up_a, _, _, _, captured = _wire(node)

    node.before_run()
    up_a.send(IoData.from_scalar(7))
    up_a.send(IoData.from_scalar(13))

    assert [int(d.payload.item()) for d in captured] == [7, 13]


def test_unconnected_optional_inputs_default_to_zero() -> None:
    """b / c / d default to 0 when their ports are unconnected, so an
    expression referencing all four still evaluates with only a wired."""
    node = Math()
    node.expression = "a + b + c + d"
    up_a, *_, captured = _wire(node)

    node.before_run()
    up_a.send(IoData.from_scalar(5))

    assert int(captured[0].payload.item()) == 5


def test_inline_default_picks_up_unconnected_optional() -> None:
    """Setting the inline-edited attribute (no upstream) propagates to
    the expression eval — mirrors the user typing 3.0 into the c
    spinner without wiring anything to it."""
    node = Math()
    node.expression = "a + c"
    node.c = 3.0
    up_a, *_, captured = _wire(node)

    node.before_run()
    up_a.send(IoData.from_scalar(10))

    assert captured[0].payload.item() == 13.0


# ── Expression syntax / function support ──────────────────────────────────────


def test_arithmetic_operators() -> None:
    node = Math()
    node.expression = "a * b + c / d"
    up_a, up_b, up_c, up_d, captured = _wire(node, connect_optional=True)

    node.before_run()
    up_a.send(IoData.from_scalar(2))
    up_b.send(IoData.from_scalar(3))
    up_c.send(IoData.from_scalar(10))
    up_d.send(IoData.from_scalar(4))

    # 2*3 + 10/4 = 6 + 2.5 = 8.5
    assert captured[-1].payload.item() == 8.5


def test_pow_floordiv_and_modulo() -> None:
    node = Math()
    node.expression = "a**2 + b % 3 + c // 2"
    up_a, up_b, up_c, up_d, captured = _wire(node, connect_optional=True)

    node.before_run()
    up_a.send(IoData.from_scalar(4))
    up_b.send(IoData.from_scalar(7))
    up_c.send(IoData.from_scalar(9))
    up_d.send(IoData.from_scalar(0))

    # 4**2 + 7%3 + 9//2 = 16 + 1 + 4 = 21
    assert int(captured[-1].payload.item()) == 21


def test_unary_negation() -> None:
    node = Math()
    node.expression = "-a + +b"
    up_a, up_b, up_c, up_d, captured = _wire(node, connect_optional=True)

    node.before_run()
    up_a.send(IoData.from_scalar(5))
    up_b.send(IoData.from_scalar(7))
    up_c.send(IoData.from_scalar(0))
    up_d.send(IoData.from_scalar(0))

    assert int(captured[-1].payload.item()) == 2


def test_trig_function_call() -> None:
    node = Math()
    node.expression = "sin(a * pi / 180)"
    up_a, *_, captured = _wire(node)

    node.before_run()
    up_a.send(IoData.from_scalar(90))

    assert abs(float(captured[-1].payload.item()) - 1.0) < 1e-9


def test_min_max_call() -> None:
    node = Math()
    node.expression = "max(a, b)"
    up_a, up_b, up_c, up_d, captured = _wire(node, connect_optional=True)

    node.before_run()
    up_a.send(IoData.from_scalar(3))
    up_b.send(IoData.from_scalar(7))
    up_c.send(IoData.from_scalar(0))
    up_d.send(IoData.from_scalar(0))

    assert int(captured[-1].payload.item()) == 7


def test_ternary_select() -> None:
    node = Math()
    node.expression = "a if b > 0 else c"
    up_a, up_b, up_c, up_d, captured = _wire(node, connect_optional=True)

    node.before_run()
    up_a.send(IoData.from_scalar(11))
    up_b.send(IoData.from_scalar(-1))
    up_c.send(IoData.from_scalar(99))
    up_d.send(IoData.from_scalar(0))

    assert int(captured[-1].payload.item()) == 99


def test_constants_pi_and_e() -> None:
    node = Math()
    node.expression = "pi + e"
    up_a, *_, captured = _wire(node)

    node.before_run()
    up_a.send(IoData.from_scalar(0))  # a unused but still triggers dispatch.

    assert abs(float(captured[-1].payload.item()) - (math.pi + math.e)) < 1e-12


def test_bool_constants_act_as_zero_and_one() -> None:
    """Literal ``True`` / ``False`` are allowed as constants because
    ``a * True`` is a useful idiom for masking out a value."""
    node = Math()
    node.expression = "a * True + b * False"
    up_a, up_b, up_c, up_d, captured = _wire(node, connect_optional=True)

    node.before_run()
    up_a.send(IoData.from_scalar(7))
    up_b.send(IoData.from_scalar(99))
    up_c.send(IoData.from_scalar(0))
    up_d.send(IoData.from_scalar(0))

    assert int(captured[-1].payload.item()) == 7


def test_uppercase_variable_names_rejected() -> None:
    """Variables are lowercase — uppercase ``A`` etc. must not work,
    so users don't end up with two parallel naming conventions in the
    same flow."""
    node = Math()
    with pytest.raises(ValueError):
        node.expression = "A + B"


# ── Safety: rejected expressions ──────────────────────────────────────────────
#
# Each entry probes a specific sandbox-escape vector or out-of-scope
# syntax. A regression that accidentally allows any of these would
# mark a real safety regression — every entry must continue to fail.

@pytest.mark.parametrize("expr", [
    # ── Direct injection via builtins / imports ──────────────────────────
    "__import__('os')",                  # __import__ not whitelisted.
    "eval('1+1')",                       # eval not whitelisted.
    "exec('print(1)')",                  # exec not whitelisted.
    "open('x')",                         # open not whitelisted.
    "compile('1', 'x', 'eval')",         # compile not whitelisted.
    "globals()",                         # globals not whitelisted.
    "locals()",                          # locals not whitelisted.

    # ── The classic CPython sandbox-escape primitive ─────────────────────
    "().__class__",
    "().__class__.__bases__[0].__subclasses__()",
    "a.__class__",
    "(1).__class__.__base__",

    # ── Attribute / item access ──────────────────────────────────────────
    "a.real",                            # Attribute on a Name.
    "a[0]",                              # Subscript.
    "a[b]",                              # Subscript with name index.
    "[a, b]",                            # List literal.
    "(a, b)",                            # Tuple literal.
    "{a: b}",                            # Dict literal.
    "{a, b}",                            # Set literal.

    # ── Comprehensions / lambdas / walrus ────────────────────────────────
    "[a for _ in (1,)]",                 # List comprehension.
    "{a: b for _ in (1,)}",              # Dict comprehension.
    "{a for _ in (1,)}",                 # Set comprehension.
    "lambda: a",                         # Lambda.
    "(x := a) + x",                      # Walrus.

    # ── String interpolation / f-string ──────────────────────────────────
    "f'{a}'",                            # f-string.

    # ── Argument / keyword tricks ────────────────────────────────────────
    "min(*[a, b])",                      # Star-args.
    "min(x=a, y=b)",                     # Keyword arg.

    # ── Unwhitelisted names / functions ──────────────────────────────────
    "z + 1",                             # Unknown variable.
    "unknown(a)",                        # Unknown function name.
    "pi(a)",                             # Constant used as a function.
    "(sin if a else cos)(b)",            # Indirect call (Call.func not
                                         # a bare ast.Name).

    # ── Unwhitelisted operators ──────────────────────────────────────────
    "a | b",                             # BitOr.
    "a & b",                             # BitAnd.
    "a ^ b",                             # BitXor.
    "a << 1",                            # LShift.
    "a >> 1",                            # RShift.
    "~a",                                # Invert.
    "a is b",                            # Identity.
    "a in (1,)",                         # Membership.

    # ── Unwhitelisted constant types ─────────────────────────────────────
    "'hello'",                           # String literal.
    "b'hello'",                          # Bytes literal.
    "...",                               # Ellipsis.
    "None",                              # NoneType — explicitly rejected.
])
def test_disallowed_expressions_rejected_at_parse_time(expr: str) -> None:
    node = Math()
    with pytest.raises(ValueError):
        node.expression = expr


def test_statements_rejected() -> None:
    """``ast.parse`` in ``mode='eval'`` rejects statements outright;
    we surface that as a ``ValueError`` along with everything else."""
    node = Math()
    for stmt in ("import os", "x = a", "del a"):
        with pytest.raises(ValueError):
            node.expression = stmt


def test_empty_expression_rejected() -> None:
    node = Math()
    with pytest.raises(ValueError, match="must not be empty"):
        node.expression = "   "


def test_syntax_error_rejected() -> None:
    node = Math()
    with pytest.raises(ValueError, match="invalid expression syntax"):
        node.expression = "a + + + "


def test_failed_set_keeps_previous_expression() -> None:
    """A bad expression must not corrupt the node's state — the
    previously-valid expression keeps evaluating."""
    node = Math()
    node.expression = "a * 2"
    with pytest.raises(ValueError):
        node.expression = "garbage syntax !!"
    # Still emits via "a * 2".
    up_a, *_, captured = _wire(node)
    node.before_run()
    up_a.send(IoData.from_scalar(5))
    assert int(captured[-1].payload.item()) == 10


def test_eval_runs_with_empty_builtins() -> None:
    """Defense-in-depth: even if validation were bypassed, the eval
    call site uses ``{"__builtins__": {}}`` — there is no fallback
    path to ``eval`` / ``exec`` / ``open`` / ``__import__`` via the
    implicit globals-builtins lookup. Verified by source inspection
    rather than runtime probe (you can't actually feed the unsafe
    AST through the public API since the setter blocks it)."""
    import inspect
    src = inspect.getsource(Math.process_impl)
    assert '"__builtins__": {}' in src


# ── Streaming behaviour ───────────────────────────────────────────────────────


def test_streams_per_frame_when_only_a_is_required() -> None:
    """Optional ports unconnected: every value on a fires the
    dispatcher, mirroring the old binary-op streaming test."""
    node = Math()
    node.expression = "a * 10"
    up_a, *_, captured = _wire(node)

    node.before_run()
    for v in (1, 2, 3):
        up_a.send(IoData.from_scalar(v))

    assert [int(d.payload.item()) for d in captured] == [10, 20, 30]


def test_input_types_restricted_to_scalar() -> None:
    """Math's inputs only declare SCALAR — an upstream IMAGE port
    can't connect, so type errors surface at link time."""
    node = Math()
    img_up = OutputPort("img", {IoDataType.IMAGE})
    for i in range(4):
        assert img_up.can_connect(node.inputs[i]) is False

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


def _wire(node: Math, n_upstreams: int = 1) -> tuple[
    list[OutputPort], list[IoData],
]:
    """Wire *n_upstreams* SCALAR upstreams + a capturing sink.

    Each upstream drives the corresponding ``v_i`` port (1-indexed
    in the expression domain, 0-indexed in the returned list). Math
    has nine optional input ports — the test only wires the first
    *n_upstreams* and leaves the rest untouched (they fall back to
    their inline default of 0.0 during eval).
    """
    upstreams: list[OutputPort] = []
    for i in range(n_upstreams):
        up = OutputPort(f"v{i + 1}_up", {IoDataType.SCALAR})
        up.connect(node.inputs[i])
        upstreams.append(up)

    captured: list[IoData] = []
    sink = InputPort("sink", {IoDataType.SCALAR})
    sink.add_listener(
        lambda: captured.append(sink.data) if sink.has_data else None
    )
    node.outputs[0].connect(sink)
    return upstreams, captured


# ── Defaults / single-input expressions ───────────────────────────────────────


def test_default_expression_passes_v1_through() -> None:
    """A brand-new node has expression='v_1'; emitting on v_1 should
    return its payload unchanged on every frame."""
    node = Math()
    (up,), captured = _wire(node, 1)

    node.before_run()
    up.send(IoData.from_scalar(7))
    up.send(IoData.from_scalar(13))

    assert [int(d.payload.item()) for d in captured] == [7, 13]


def test_unconnected_inputs_default_to_zero() -> None:
    """Inputs the expression references but the user hasn't wired up
    fall back to the inline default 0.0, so an expression referencing
    several slots still evaluates with only one wired."""
    node = Math()
    node.expression = "v_1 + v_2 + v_3 + v_4"
    (up,), captured = _wire(node, 1)

    node.before_run()
    up.send(IoData.from_scalar(5))

    assert int(captured[0].payload.item()) == 5


def test_inline_default_picks_up_unconnected_port() -> None:
    """Editing the inline default on an unconnected port (mimics the
    user typing 3.0 into the v_3 spinner) propagates to the eval."""
    node = Math()
    node.expression = "v_1 + v_3"
    node.inputs[2].default_value = 3.0
    (up,), captured = _wire(node, 1)

    node.before_run()
    up.send(IoData.from_scalar(10))

    assert captured[0].payload.item() == 13.0


def test_inline_widget_setattr_picks_up_unconnected_port() -> None:
    """The inline-row spinner writes via ``setattr(node, port.name, …)``
    (because dynamic ports have no descriptor); ``process_impl`` must
    pick that up via ``getattr`` so the slider value reaches eval."""
    node = Math()
    node.expression = "v_1 + v_2"
    # Mimic what the inline FLOAT widget does on value change:
    node.v_2 = 4.0  # type: ignore[attr-defined]
    (up,), captured = _wire(node, 1)

    node.before_run()
    up.send(IoData.from_scalar(10))

    assert captured[0].payload.item() == 14.0


# ── Topology ──────────────────────────────────────────────────────────────────


def test_has_nine_input_ports() -> None:
    """Backend always carries the full pool of nine ``v_i`` ports
    regardless of how many the editor currently shows."""
    node = Math()
    assert [p.name for p in node.inputs] == [f"v_{i}" for i in range(1, 10)]


def test_show_only_used_inputs_is_set() -> None:
    """Math opts the editor into the "hide trailing rows" UI mode."""
    assert Math.SHOW_ONLY_USED_INPUTS is True


# ── Expression syntax / function support ──────────────────────────────────────


def test_arithmetic_operators() -> None:
    node = Math()
    node.expression = "v_1 * v_2 + v_3 / v_4"
    upstreams, captured = _wire(node, 4)

    node.before_run()
    upstreams[0].send(IoData.from_scalar(2))
    upstreams[1].send(IoData.from_scalar(3))
    upstreams[2].send(IoData.from_scalar(10))
    upstreams[3].send(IoData.from_scalar(4))

    # 2*3 + 10/4 = 6 + 2.5 = 8.5
    assert captured[-1].payload.item() == 8.5


def test_pow_floordiv_and_modulo() -> None:
    node = Math()
    node.expression = "v_1**2 + v_2 % 3 + v_3 // 2"
    upstreams, captured = _wire(node, 3)

    node.before_run()
    upstreams[0].send(IoData.from_scalar(4))
    upstreams[1].send(IoData.from_scalar(7))
    upstreams[2].send(IoData.from_scalar(9))

    # 4**2 + 7%3 + 9//2 = 16 + 1 + 4 = 21
    assert int(captured[-1].payload.item()) == 21


def test_unary_negation() -> None:
    node = Math()
    node.expression = "-v_1 + +v_2"
    upstreams, captured = _wire(node, 2)

    node.before_run()
    upstreams[0].send(IoData.from_scalar(5))
    upstreams[1].send(IoData.from_scalar(7))

    assert int(captured[-1].payload.item()) == 2


def test_trig_function_call() -> None:
    node = Math()
    node.expression = "sin(v_1 * pi / 180)"
    (up,), captured = _wire(node, 1)

    node.before_run()
    up.send(IoData.from_scalar(90))

    assert abs(float(captured[-1].payload.item()) - 1.0) < 1e-9


def test_min_max_call() -> None:
    node = Math()
    node.expression = "max(v_1, v_2)"
    upstreams, captured = _wire(node, 2)

    node.before_run()
    upstreams[0].send(IoData.from_scalar(3))
    upstreams[1].send(IoData.from_scalar(7))

    assert int(captured[-1].payload.item()) == 7


def test_ternary_select() -> None:
    node = Math()
    node.expression = "v_1 if v_2 > 0 else v_3"
    upstreams, captured = _wire(node, 3)

    node.before_run()
    upstreams[0].send(IoData.from_scalar(11))
    upstreams[1].send(IoData.from_scalar(-1))
    upstreams[2].send(IoData.from_scalar(99))

    assert int(captured[-1].payload.item()) == 99


def test_constants_pi_and_e() -> None:
    node = Math()
    node.expression = "v_1 * 0 + pi + e"
    (up,), captured = _wire(node, 1)

    node.before_run()
    up.send(IoData.from_scalar(0))

    assert abs(float(captured[-1].payload.item()) - (math.pi + math.e)) < 1e-12


def test_bool_constants_act_as_zero_and_one() -> None:
    """Literal ``True`` / ``False`` are allowed as constants because
    ``v_1 * True`` is a useful idiom for masking out a value."""
    node = Math()
    node.expression = "v_1 * True + v_2 * False"
    upstreams, captured = _wire(node, 2)

    node.before_run()
    upstreams[0].send(IoData.from_scalar(7))
    upstreams[1].send(IoData.from_scalar(99))

    assert int(captured[-1].payload.item()) == 7


def test_unknown_v_index_rejected_at_parse_time() -> None:
    """``v_10`` and similar are simply unknown names — rejected at
    parse time by the Name-whitelist check."""
    node = Math()
    for bad in ("v_0", "v_10", "v_42"):
        with pytest.raises(ValueError, match="unknown name"):
            node.expression = bad


def test_bare_v_rejected_at_parse_time() -> None:
    """Bare ``v`` is not on the name whitelist — rejected at edit time."""
    node = Math()
    for bad in ("v", "v + 1", "sin(v)"):
        with pytest.raises(ValueError, match="unknown name"):
            node.expression = bad


def test_subscript_rejected_at_parse_time() -> None:
    """Subscript syntax is not on the AST whitelist — old ``v[1]``
    style expressions fail loudly so a stale flow surfaces an error
    instead of silently mis-evaluating."""
    node = Math()
    for bad in ("v_1[0]", "v_1[1:2]", "(v_1, v_2)[0]"):
        with pytest.raises(ValueError, match="disallowed expression element"):
            node.expression = bad


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
    "v_1.__class__",
    "(1).__class__.__base__",

    # ── Attribute / subscript / collection literals ──────────────────────
    "v_1.real",                          # Attribute on a Name.
    "v_1[0]",                            # Subscript (whole class banned).
    "[v_1, v_2]",                        # List literal.
    "(v_1, v_2)",                        # Tuple literal.
    "{v_1: v_2}",                        # Dict literal.
    "{v_1, v_2}",                        # Set literal.

    # ── Comprehensions / lambdas / walrus ────────────────────────────────
    "[v_1 for _ in (1,)]",               # List comprehension.
    "{v_1: v_2 for _ in (1,)}",          # Dict comprehension.
    "{v_1 for _ in (1,)}",               # Set comprehension.
    "lambda: v_1",                       # Lambda.
    "(x := v_1) + x",                    # Walrus.

    # ── String interpolation / f-string ──────────────────────────────────
    "f'{v_1}'",                          # f-string.

    # ── Argument / keyword tricks ────────────────────────────────────────
    "min(*[v_1, v_2])",                  # Star-args.
    "min(x=v_1, y=v_2)",                 # Keyword arg.

    # ── Unwhitelisted names / functions ──────────────────────────────────
    "z + 1",                             # Unknown variable.
    "unknown(v_1)",                      # Unknown function name.
    "pi(v_1)",                           # Constant used as a function.
    "(sin if v_1 else cos)(v_2)",        # Indirect call.

    # ── Unwhitelisted operators ──────────────────────────────────────────
    "v_1 | v_2",                         # BitOr.
    "v_1 & v_2",                         # BitAnd.
    "v_1 ^ v_2",                         # BitXor.
    "v_1 << 1",                          # LShift.
    "v_1 >> 1",                          # RShift.
    "~v_1",                              # Invert.
    "v_1 is v_2",                        # Identity.
    "v_1 in (1,)",                       # Membership.

    # ── Unwhitelisted constant types ─────────────────────────────────────
    "'hello'",                           # String literal.
    "b'hello'",                          # Bytes literal.
    "...",                               # Ellipsis.
    "None",                              # NoneType — explicitly rejected.
])
def test_disallowed_expressions_rejected_at_parse_time(expr: str) -> None:
    node = Math()
    with pytest.raises((ValueError, TypeError)):
        node.expression = expr


def test_statements_rejected() -> None:
    """``ast.parse`` in ``mode='eval'`` rejects statements outright;
    we surface that as a ``ValueError`` along with everything else."""
    node = Math()
    for stmt in ("import os", "x = v_1", "del v_1"):
        with pytest.raises(ValueError):
            node.expression = stmt


def test_empty_expression_rejected() -> None:
    node = Math()
    with pytest.raises(ValueError, match="must not be empty"):
        node.expression = "   "


def test_syntax_error_rejected() -> None:
    node = Math()
    with pytest.raises(ValueError, match="invalid expression syntax"):
        node.expression = "v_1 + + + "


def test_failed_set_keeps_previous_expression() -> None:
    """A bad expression must not corrupt the node's state — the
    previously-valid expression keeps evaluating."""
    node = Math()
    node.expression = "v_1 * 2"
    with pytest.raises(ValueError):
        node.expression = "garbage syntax !!"
    # Still emits via "v_1 * 2".
    (up,), captured = _wire(node, 1)
    node.before_run()
    up.send(IoData.from_scalar(5))
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


def test_streams_per_frame_when_only_v1_connected() -> None:
    """A single-input flow fires the dispatcher per frame on v_1."""
    node = Math()
    node.expression = "v_1 * 10"
    (up,), captured = _wire(node, 1)

    node.before_run()
    for v in (1, 2, 3):
        up.send(IoData.from_scalar(v))

    assert [int(d.payload.item()) for d in captured] == [10, 20, 30]


def test_input_types_restricted_to_scalar() -> None:
    """Math's inputs only declare SCALAR — an upstream IMAGE port
    can't connect, so type errors surface at link time."""
    node = Math()
    img_up = OutputPort("img", {IoDataType.IMAGE})
    for port in node.inputs:
        assert img_up.can_connect(port) is False

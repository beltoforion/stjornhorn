"""Class-level parameter descriptors for :class:`~core.node_base.NodeBase`.

A descriptor declared at class level on a node subclass replaces the
old triple-declaration pattern (``self._<name>`` init + ``InputPort``
construction + ``@property``/``@setter``) with a single line:

.. code-block:: python

    class GaussianBlur(NodeBase):
        ksize = OddIntParam(5, min=1, unit="px", description="...")
        sigma = FloatParam(0.0, min=0.0, description="...")

The descriptor owns:

* the storage slot (``self._<name>``),
* type coercion (``_coerce``) and validation (``_validate``),
* the metadata bundle the UI's param-widget builder consumes,
* the :class:`~core.port.InputPort` factory.

Domain-specific subclasses (e.g. :class:`OddIntParam`) extend
``_coerce`` / ``_validate`` for shared invariants — kernel-size must be
odd, value must be a probability in [0, 1], etc. — so the rule lives
in one place instead of being re-implemented inside every node's
setter.

Backlog item H2 (see ``refacturing.txt``).
"""
from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any

from core.io_data import IoDataType
from core.node_base import NodeParamType
from core.port import InputPort

if TYPE_CHECKING:
    pass


class _ParamBase:
    """Abstract base for class-level node-parameter descriptors.

    Subclasses must set :attr:`_NODE_PARAM_TYPE` (drives widget choice)
    and :attr:`_PORT_TYPE` (the :class:`~core.io_data.IoDataType` of the
    auto-created input port). They override :meth:`_coerce` and
    :meth:`_validate` to enforce per-type invariants.

    The optional class attribute :attr:`WIDGET_CLASS` lets a subclass
    short-circuit the param-widget factory and ship its own widget
    (e.g. :class:`OddIntParam` driving an _OddSpinBox-backed editor)
    without growing the per-NodeParamType dispatch table.
    """

    _NODE_PARAM_TYPE: NodeParamType
    _PORT_TYPE: IoDataType
    #: Optional widget override consulted by the param-widget builder.
    #: ``None`` (the default) means "use the registry's per-NodeParamType
    #: default widget".
    WIDGET_CLASS: type | None = None

    def __init__(
        self,
        default: object,
        *,
        unit: str | None = None,
        description: str | None = None,
        optional: bool = True,
    ) -> None:
        self.default: object = default
        self.unit: str | None = unit
        self.description: str | None = description
        self.optional: bool = optional
        # Set by __set_name__ when the descriptor is bound to its class.
        self.name: str = ""
        self._private: str = ""

    # ── Descriptor protocol ────────────────────────────────────────────────────

    def __set_name__(self, owner: type, name: str) -> None:
        self.name = name
        self._private = f"_{name}"

    def __get__(self, instance: object, owner: type | None = None) -> Any:
        if instance is None:
            return self
        return getattr(instance, self._private)

    def __set__(self, instance: object, value: object) -> None:
        coerced = self._coerce(value)
        self._validate(coerced)
        shaped = self._shape(coerced)
        object.__setattr__(instance, self._private, shaped)

    # ── Hooks for subclasses ───────────────────────────────────────────────────

    def _coerce(self, value: object) -> Any:
        """Convert *value* to the descriptor's storage type.

        Default: identity. Numeric subclasses override to ``int(value)``
        / ``float(value)``. The result of ``_coerce`` is what
        :meth:`_validate` sees, so range checks reject literal user
        input *before* any domain-specific shaping rounds it into a
        valid form.
        """
        return value

    def _validate(self, value: Any) -> None:
        """Raise on out-of-range / invalid values. Default: no-op.

        Subclasses with declared bounds (``min`` / ``max``) raise
        :class:`ValueError` here so a mis-set value fails loudly at the
        property assignment, not at downstream-consumer time. Runs on
        the type-coerced (but not yet shaped) value so the user can't
        bypass the bound by feeding a value the shape hook would round
        into range.
        """

    def _shape(self, value: Any) -> Any:
        """Apply domain-specific shaping after validation passes.

        Default: identity. Domain subclasses (e.g. :class:`OddIntParam`)
        override to round the validated value into its canonical form
        — odd integer, probability ∈ [0, 1], wrapped angle, etc.
        Running after :meth:`_validate` means a user-supplied value
        that's out of range fails at assignment time even when the
        shape hook *could* have rounded it into range.
        """
        return value

    # ── InputPort factory ──────────────────────────────────────────────────────

    def _build_metadata(self) -> dict[str, object]:
        """Compose the metadata bundle for the auto-created InputPort.

        Subclasses override to add type-specific keys (``min``, ``max``,
        ``step``, ``decimals``, ``enum``, ``placeholder`` …). The base
        contributes the universal keys: ``param_type``, ``default``,
        and the optional ``unit`` / ``description`` if provided.
        """
        meta: dict[str, object] = {
            "param_type": self._NODE_PARAM_TYPE,
            "default": self.default,
        }
        if self.unit is not None:
            meta["unit"] = self.unit
        if self.description is not None:
            meta["description"] = self.description
        return meta

    def make_port(self) -> InputPort:
        """Build the :class:`InputPort` this descriptor advertises.

        Called once per node instance from
        :meth:`~core.node_base.NodeBase._apply_default_params` so every
        node with descriptor-style params gets the matching
        upstream-driveable input port for free.
        """
        return InputPort(
            self.name,
            {self._PORT_TYPE},
            optional=self.optional,
            default_value=self.default,
            metadata=self._build_metadata(),
        )


class IntParam(_ParamBase):
    """Integer node parameter.

    Coerces incoming values via ``int(value)``. Optional ``min`` /
    ``max`` bounds raise :class:`ValueError` on out-of-range writes.
    """

    _NODE_PARAM_TYPE = NodeParamType.INT
    _PORT_TYPE = IoDataType.SCALAR

    def __init__(
        self,
        default: int,
        *,
        min: int | None = None,
        max: int | None = None,
        unit: str | None = None,
        description: str | None = None,
        optional: bool = True,
    ) -> None:
        super().__init__(
            default,
            unit=unit,
            description=description,
            optional=optional,
        )
        self.min: int | None = min
        self.max: int | None = max

    def _coerce(self, value: object) -> int:
        return int(value)

    def _validate(self, value: int) -> None:
        if self.min is not None and value < self.min:
            raise ValueError(
                f"{self.name} must be >= {self.min} (got {value})"
            )
        if self.max is not None and value > self.max:
            raise ValueError(
                f"{self.name} must be <= {self.max} (got {value})"
            )

    def _build_metadata(self) -> dict[str, object]:
        meta = super()._build_metadata()
        if self.min is not None:
            meta["min"] = self.min
        if self.max is not None:
            meta["max"] = self.max
        return meta


class OddIntParam(IntParam):
    """Integer parameter shaped to the nearest odd value (rounding up).

    Shared invariant for OpenCV-style kernel-size params: Gaussian /
    Median / Bilateral / box filters all require an odd kernel side
    length. Without this descriptor each node would re-implement
    ``v + 1 if v % 2 == 0 else v`` in its own setter; collecting it
    here means the rule is named once and any future filter that needs
    odd-only ints picks it up by changing one declaration.

    Shaping runs *after* :meth:`_validate`, so a literal value below
    ``min`` raises rather than being shaped up into range — matches
    the behaviour of the hand-rolled setters this descriptor replaces
    (e.g. the legacy ``Median.size`` rejected ``0`` outright instead
    of silently bumping it to ``1``).
    """

    def _shape(self, value: int) -> int:
        return value + 1 if value % 2 == 0 else value


class FloatParam(_ParamBase):
    """Floating-point node parameter.

    Coerces incoming values via ``float(value)``. Optional ``min`` /
    ``max`` bounds raise :class:`ValueError` on out-of-range writes.
    Set ``min_exclusive=True`` / ``max_exclusive=True`` to make the
    bound strict (``> min`` rather than ``>= min``) — used e.g. by
    ``Overlay.scale`` which must be strictly positive.
    ``step`` and ``decimals`` flow into the spin-box widget metadata.
    """

    _NODE_PARAM_TYPE = NodeParamType.FLOAT
    _PORT_TYPE = IoDataType.SCALAR

    def __init__(
        self,
        default: float,
        *,
        min: float | None = None,
        max: float | None = None,
        min_exclusive: bool = False,
        max_exclusive: bool = False,
        step: float | None = None,
        decimals: int | None = None,
        unit: str | None = None,
        description: str | None = None,
        optional: bool = True,
    ) -> None:
        super().__init__(
            default,
            unit=unit,
            description=description,
            optional=optional,
        )
        self.min: float | None = min
        self.max: float | None = max
        self.min_exclusive: bool = min_exclusive
        self.max_exclusive: bool = max_exclusive
        self.step: float | None = step
        self.decimals: int | None = decimals

    def _coerce(self, value: object) -> float:
        return float(value)

    def _validate(self, value: float) -> None:
        if self.min is not None:
            below = value <= self.min if self.min_exclusive else value < self.min
            if below:
                op = ">" if self.min_exclusive else ">="
                raise ValueError(
                    f"{self.name} must be {op} {self.min} (got {value})"
                )
        if self.max is not None:
            above = value >= self.max if self.max_exclusive else value > self.max
            if above:
                op = "<" if self.max_exclusive else "<="
                raise ValueError(
                    f"{self.name} must be {op} {self.max} (got {value})"
                )

    def _build_metadata(self) -> dict[str, object]:
        meta = super()._build_metadata()
        if self.min is not None:
            meta["min"] = self.min
        if self.max is not None:
            meta["max"] = self.max
        if self.step is not None:
            meta["step"] = self.step
        if self.decimals is not None:
            meta["decimals"] = self.decimals
        return meta


class ClampedFloatParam(FloatParam):
    """Float parameter whose ``min`` / ``max`` clamp rather than raise.

    Use when out-of-range input is a UX choice, not a user error — e.g.
    an opacity slider where 1.5 is conceptually just 1.0 ("fully
    opaque") and a negative value is just 0.0 ("fully transparent").
    Validation is suppressed and the bounds are enforced by
    :meth:`_shape` instead, so the widget still gets ``min`` / ``max``
    in its metadata (the spin-box stays bounded) but a port-driven or
    programmatic write that lands outside the range is silently clamped
    rather than rejected.

    Both bounds are inclusive — the exclusive variants
    (``min_exclusive`` / ``max_exclusive``) on :class:`FloatParam` do
    not apply here because clamping a value to an open bound is
    ill-defined.
    """

    def _validate(self, value: float) -> None:
        # Bounds enforced via _shape (clamp), not _validate (raise).
        pass

    def _shape(self, value: float) -> float:
        if self.min is not None and value < self.min:
            return self.min
        if self.max is not None and value > self.max:
            return self.max
        return value


class BoolParam(_ParamBase):
    """Boolean node parameter.

    Coerces incoming values via ``bool(value)``. No validation hook
    needed — every value Python accepts as truthy/falsy is valid.
    """

    _NODE_PARAM_TYPE = NodeParamType.BOOL
    _PORT_TYPE = IoDataType.BOOL

    def __init__(
        self,
        default: bool,
        *,
        description: str | None = None,
        optional: bool = True,
    ) -> None:
        super().__init__(
            default,
            description=description,
            optional=optional,
        )

    def _coerce(self, value: object) -> bool:
        return bool(value)


class EnumParam(_ParamBase):
    """Enum-valued node parameter.

    The enum class is required; the descriptor stores the chosen
    member, the :class:`InputPort` carries the class itself in its
    metadata under ``"enum"`` so the param-widget builder can populate
    the combo box.

    Coercion accepts the enum member, its ``.value``, or its ``.name``
    (string), to make ``__set__`` forgiving for port-driven streams
    that may carry either form. Raises :class:`ValueError` if the
    incoming value can't be mapped to a member of the enum.
    """

    _NODE_PARAM_TYPE = NodeParamType.ENUM
    _PORT_TYPE = IoDataType.ENUM

    def __init__(
        self,
        enum_cls: type[Enum],
        default: Enum,
        *,
        description: str | None = None,
        optional: bool = True,
    ) -> None:
        if not (isinstance(enum_cls, type) and issubclass(enum_cls, Enum)):
            raise TypeError(
                f"EnumParam requires an Enum subclass, got {enum_cls!r}"
            )
        if not isinstance(default, enum_cls):
            raise TypeError(
                f"EnumParam default {default!r} is not a member of {enum_cls.__name__}"
            )
        super().__init__(
            default,
            description=description,
            optional=optional,
        )
        self.enum_cls: type[Enum] = enum_cls

    def _coerce(self, value: object) -> Enum:
        if isinstance(value, self.enum_cls):
            return value
        try:
            return self.enum_cls(value)
        except (ValueError, KeyError):
            pass
        if isinstance(value, str):
            try:
                return self.enum_cls[value]
            except KeyError:
                pass
        raise ValueError(
            f"{self.name}: cannot map {value!r} to a {self.enum_cls.__name__} member"
        )

    def _build_metadata(self) -> dict[str, object]:
        meta = super()._build_metadata()
        meta["enum"] = self.enum_cls
        return meta


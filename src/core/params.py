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
        object.__setattr__(instance, self._private, coerced)

    # ── Hooks for subclasses ───────────────────────────────────────────────────

    def _coerce(self, value: object) -> Any:
        """Convert *value* to the descriptor's storage type.

        Default: identity. Numeric subclasses override to ``int(value)``
        / ``float(value)``; domain subclasses (e.g. :class:`OddIntParam`)
        chain into ``super()._coerce`` and apply additional shaping.
        """
        return value

    def _validate(self, value: Any) -> None:
        """Raise on out-of-range / invalid values. Default: no-op.

        Subclasses with declared bounds (``min`` / ``max``) raise
        :class:`ValueError` here so a mis-set value fails loudly at the
        property assignment, not at downstream-consumer time.
        """

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
    """Integer parameter coerced to the nearest odd value (rounding up).

    Shared invariant for OpenCV-style kernel-size params: Gaussian /
    Median / Bilateral / box filters all require an odd kernel side
    length. Without this descriptor each node would re-implement
    ``v + 1 if v % 2 == 0 else v`` in its own setter; collecting it
    here means the rule is named once and any future filter that needs
    odd-only ints picks it up by changing one declaration.
    """

    def _coerce(self, value: object) -> int:
        v = super()._coerce(value)
        return v + 1 if v % 2 == 0 else v


class FloatParam(_ParamBase):
    """Floating-point node parameter.

    Coerces incoming values via ``float(value)``. Optional ``min`` /
    ``max`` bounds raise :class:`ValueError` on out-of-range writes.
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
        self.step: float | None = step
        self.decimals: int | None = decimals

    def _coerce(self, value: object) -> float:
        return float(value)

    def _validate(self, value: float) -> None:
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
        if self.step is not None:
            meta["step"] = self.step
        if self.decimals is not None:
            meta["decimals"] = self.decimals
        return meta

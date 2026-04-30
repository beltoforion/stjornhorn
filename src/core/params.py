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
from pathlib import Path
from typing import Any

from core.io_data import IoDataType
from core.node_base import NodeParamType
from core.port import InputPort


class _ParamBase:
    """Abstract base for class-level node-parameter descriptors.

    Subclasses must set :attr:`_NODE_PARAM_TYPE` (drives widget choice)
    and :attr:`_PORT_TYPE` (the :class:`~core.io_data.IoDataType` of the
    auto-created input port). They override :meth:`_coerce` and
    :meth:`_validate` to enforce per-type invariants.

    A descriptor that needs a widget more specific than its
    :class:`NodeParamType` default (e.g. :class:`OddIntParam` wanting an
    odd-only spin box) sets :attr:`_WIDGET_KIND` to a string identifier
    that the UI's param-widget factory looks up in its kind registry
    before falling back to the per-:class:`NodeParamType` table. The
    string indirection keeps ``core.params`` free of any ``ui.*``
    import.
    """

    _NODE_PARAM_TYPE: NodeParamType
    _PORT_TYPE: IoDataType
    #: Python type stored in the backing ``_<name>`` slot.  Subclasses
    #: override this so :meth:`__set_name__` can annotate the owner class
    #: and give static type-checkers (Pylance / pyright) visibility of
    #: the otherwise-dynamic attribute.
    _BACKING_TYPE: type = object
    #: Optional widget-kind identifier consulted by the param-widget
    #: factory before its default per-:class:`NodeParamType` dispatch.
    #: ``None`` means "use the default widget for my param type".
    _WIDGET_KIND: str | None = None

    def __init__(
        self,
        default: object,
        *,
        unit: str | None = None,
        description: str | None = None,
        optional: bool = True,
        constant: bool = False,
    ) -> None:
        self.default: object = default
        self.unit: str | None = unit
        self.description: str | None = description
        self.optional: bool = optional
        # ``constant=True`` declares a node-level parameter that's
        # *not* drivable from upstream (file path on a source, codec
        # choice on a sink, colormap selection on a visualisation
        # node). NodeBase registers it via ``_add_param`` instead of
        # auto-creating an :class:`InputPort`, so the UI renders it
        # inline with no socket dot — matching the legacy
        # :class:`~core.node_base.NodeParam` UX.
        self.constant: bool = constant
        # Set by __set_name__ when the descriptor is bound to its class.
        self.name: str = ""
        self._private: str = ""
        # Lazy-built and cached so the UI can read .metadata as if the
        # descriptor were a NodeParam (which exposes a plain dict).
        self._cached_metadata: dict[str, object] | None = None

    # ── Descriptor protocol ────────────────────────────────────────────────────

    def __set_name__(self, owner: type, name: str) -> None:
        self.name = name
        self._private = f"_{name}"
        # Annotate the backing attribute on the owner class so that static
        # type-checkers (Pylance / pyright) recognise ``self._<name>`` as a
        # known attribute with the correct type.  We write directly into
        # owner.__dict__["__annotations__"] (via the class-level assignment
        # below) to avoid touching parent-class annotation dicts.
        ann = vars(owner).get("__annotations__", {})
        ann[self._private] = self._BACKING_TYPE
        owner.__annotations__ = ann

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
        if self._WIDGET_KIND is not None:
            meta["widget_kind"] = self._WIDGET_KIND
        return meta

    def make_port(self) -> InputPort:
        """Build the :class:`InputPort` this descriptor advertises.

        Called once per node instance from
        :meth:`~core.node_base.NodeBase._apply_default_params` so every
        node with descriptor-style params gets the matching
        upstream-driveable input port for free. Only invoked when
        ``constant=False``; constant descriptors register themselves
        as :class:`~core.node_base.NodeParam`-shaped entries on
        ``node.params`` instead.
        """
        return InputPort(
            self.name,
            {self._PORT_TYPE},
            optional=self.optional,
            default_value=self.default,
            metadata=self.metadata,
        )

    # ── NodeParam-compatible read interface ────────────────────────────────────
    #
    # When ``constant=True`` the descriptor itself is appended to
    # ``node._params`` and the UI's existing dispatch on
    # :class:`~core.node_base.NodeParam` picks it up. NodeParam exposes
    # ``name``, ``metadata``, ``default_value`` and ``upstream``; the
    # descriptor already has ``name``, and these three properties round
    # out the contract so the UI doesn't have to special-case
    # descriptor-backed params.

    @property
    def metadata(self) -> dict[str, object]:
        """Lazily-built metadata dict, cached after first access.

        The dict contents never change after class definition (it
        captures the descriptor's declared min / max / unit / description
        / etc.) so caching is safe and avoids rebuilding on every UI
        read of a constant param.
        """
        if self._cached_metadata is None:
            self._cached_metadata = self._build_metadata()
        return self._cached_metadata

    @property
    def default_value(self) -> object:
        """Alias for :attr:`default` matching the NodeParam interface."""
        return self.default

    @property
    def upstream(self) -> None:
        """Always ``None``; descriptors are not upstream-driven on the
        ``node.params`` path. Mirrors :attr:`NodeParam.upstream`."""
        return None


class IntParam(_ParamBase):
    """Integer node parameter.

    Coerces incoming values via ``int(value)``. Optional ``min`` /
    ``max`` bounds raise :class:`ValueError` on out-of-range writes.
    """

    _NODE_PARAM_TYPE = NodeParamType.INT
    _PORT_TYPE = IoDataType.SCALAR
    _BACKING_TYPE = int

    def __init__(
        self,
        default: int,
        *,
        min: int | None = None,
        max: int | None = None,
        unit: str | None = None,
        description: str | None = None,
        optional: bool = True,
        constant: bool = False,
    ) -> None:
        super().__init__(
            default,
            unit=unit,
            description=description,
            optional=optional,
            constant=constant,
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

    Advertises ``widget_kind="odd_int"`` so the editor uses an
    odd-only :class:`QSpinBox` subclass: the up/down arrows step in
    twos and a typed even value is rejected at validation time and
    fixed up to the next odd integer on focus loss — matching what
    the descriptor itself does on assignment.
    """

    _WIDGET_KIND = "odd_int"

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
    _BACKING_TYPE = float

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
        constant: bool = False,
    ) -> None:
        super().__init__(
            default,
            unit=unit,
            description=description,
            optional=optional,
            constant=constant,
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
    _BACKING_TYPE = bool

    def __init__(
        self,
        default: bool,
        *,
        description: str | None = None,
        optional: bool = True,
        constant: bool = False,
    ) -> None:
        super().__init__(
            default,
            description=description,
            optional=optional,
            constant=constant,
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
    _BACKING_TYPE = Enum

    def __init__(
        self,
        enum_cls: type[Enum],
        default: Enum,
        *,
        description: str | None = None,
        optional: bool = True,
        constant: bool = False,
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
            constant=constant,
        )
        self.enum_cls: type[Enum] = enum_cls

    def __set_name__(self, owner: type, name: str) -> None:
        self._BACKING_TYPE = self.enum_cls
        super().__set_name__(owner, name)

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



class StringParam(_ParamBase):
    """String node parameter.

    Coerces incoming values via ``str(value)``. Optional ``placeholder``
    is rendered by the line-edit widget when the field is empty;
    optional ``max_length`` caps the typed text at the widget level (the
    descriptor still accepts arbitrary input, the widget enforces).
    """

    _NODE_PARAM_TYPE = NodeParamType.STRING
    _PORT_TYPE = IoDataType.STRING
    _BACKING_TYPE = str

    def __init__(
        self,
        default: str = "",
        *,
        placeholder: str | None = None,
        max_length: int | None = None,
        description: str | None = None,
        optional: bool = True,
        constant: bool = False,
    ) -> None:
        super().__init__(
            default,
            description=description,
            optional=optional,
            constant=constant,
        )
        self.placeholder: str | None = placeholder
        self.max_length: int | None = max_length

    def _coerce(self, value: object) -> str:
        return str(value)

    def _build_metadata(self) -> dict[str, object]:
        meta = super()._build_metadata()
        if self.placeholder is not None:
            meta["placeholder"] = self.placeholder
        if self.max_length is not None:
            meta["max_length"] = self.max_length
        return meta


class FilePathParam(_ParamBase):
    """File-path node parameter (open / save / directory).

    The widget renders a line edit + browse button + view-in-OS button.
    ``mode`` selects the dialog flavour:

      * ``"open"`` (default) — pick an existing file.
      * ``"save"`` — choose a destination file (can be new).
      * ``"directory"`` — pick a folder.

    ``filter`` is the file-dialog filter string (e.g.
    ``"PNG (*.png);;All files (*)"``); ignored in directory mode.
    ``base_dir`` is the root for relative paths the line edit displays
    *and* the anchor :func:`core.path_utils.store_relative_to` uses
    when normalising an incoming path. ``None`` skips the normalising
    step and lets the widget pick the display fallback
    (``constants.OUTPUT_DIR`` for save mode, ``constants.INPUT_DIR``
    otherwise — same fallback the legacy hand-rolled widget used).

    Storage type is :class:`pathlib.Path`. ``_coerce`` runs incoming
    str / Path inputs through :func:`store_relative_to(base_dir)` so
    paths inside ``base_dir`` are stashed in their portable relative
    form (matching the saved-flow representation). When ``base_dir``
    is ``None`` the value is converted to :class:`Path` unchanged.
    """

    _NODE_PARAM_TYPE = NodeParamType.FILE_PATH
    _PORT_TYPE = IoDataType.PATH
    _BACKING_TYPE = str

    _VALID_MODES = ("open", "save", "directory")

    def __init__(
        self,
        default: str | Path = "",
        *,
        mode: str = "open",
        filter: str | None = None,
        base_dir: Path | None = None,
        caption: str | None = None,
        description: str | None = None,
        optional: bool = True,
        constant: bool = False,
    ) -> None:
        if mode not in self._VALID_MODES:
            raise ValueError(
                f"FilePathParam mode must be one of {self._VALID_MODES} "
                f"(got {mode!r})"
            )
        super().__init__(
            default,
            description=description,
            optional=optional,
            constant=constant,
        )
        self.mode: str = mode
        self.filter: str | None = filter
        self.base_dir: Path | None = base_dir
        self.caption: str | None = caption

    def _coerce(self, value: object) -> Path:
        # Late import — path_utils sits below the core/ tree and pulling
        # it in at module load time would extend the import graph for
        # every node that doesn't actually use a FilePathParam.
        from core.path_utils import store_relative_to

        if self.base_dir is not None:
            return store_relative_to(value, self.base_dir)
        return Path(value) if not isinstance(value, Path) else value

    def _build_metadata(self) -> dict[str, object]:
        meta = super()._build_metadata()
        # The widget reads ``mode`` / ``filter`` / ``base_dir`` /
        # ``caption`` from metadata; only emit non-default values to
        # keep the dict small and the saved-flow representation tidy.
        if self.mode != "open":
            meta["mode"] = self.mode
        if self.filter is not None:
            meta["filter"] = self.filter
        if self.base_dir is not None:
            meta["base_dir"] = self.base_dir
        if self.caption is not None:
            meta["caption"] = self.caption
        return meta

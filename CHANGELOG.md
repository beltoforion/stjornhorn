# Changelog

All notable changes to Stjörnhorn (repo: `image-inquest`) are tracked
in this file.

The format loosely follows [Keep a
Changelog](https://keepachangelog.com/en/1.1.0/) and the project aims
to adhere to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
once a first tagged release is cut.

## [Unreleased]

## [0.1.44] — 2026-04-26

### Fixed
- **QCheckBox check glyph renders again.** Same Qt stylesheet
  rendering-mode quirk that was hiding spinbox arrows and combobox
  chevrons — the ``QCheckBox::indicator:checked`` rule set
  background and border colours but never drew the actual check
  mark, so toggling a checkbox just turned the box blue without
  showing a tick. A new ``checkmark.svg`` asset (white stroke,
  14×14, sized to match the indicator) is wired into the indicator
  via ``image: url(...)``, with the same theme-apply-time path
  injection the spinbox arrows use.

### Added
- ``assets/icons/checkmark.svg``: stroke-only white checkmark,
  rendered at the indicator's 14×14 px so the tick reads cleanly
  against the checked-fill blue.

## [0.1.43] — 2026-04-26

### Fixed
- **QComboBox dropdown chevron renders again.** Same Qt stylesheet
  rendering-mode quirk that hid the QSpinBox up/down arrows in
  0.1.41 — once a stylesheet rule lands on a QComboBox (background /
  border / padding from the shared input rule), Qt drops the native
  chevron drawing for the drop-down sub-control unless an explicit
  ``image`` rule on ``::down-arrow`` provides one. Adds
  ``QComboBox::drop-down`` (geometry pinned to the right edge with a
  16-px column and dark separator) and ``QComboBox::down-arrow``
  (reuses the ``spinner_down.svg`` asset shipped in 0.1.41) plus a
  ``::drop-down:hover`` highlight to match the spinbox button
  feedback.

## [0.1.42] — 2026-04-26

### Removed
- **Live-preview auto-run.** ``NodeEditorPage`` previously had a 300 ms
  debounced QTimer (``_live_timer``) that fired ``_on_run_clicked``
  every time a param changed and the flow contained at least one
  reactive source. The user reported the feature as racy — clicking
  a spinner was kicking off a fresh run mid-edit. The whole
  mechanism is gone:
  - ``_live_timer`` field + setup deleted.
  - ``_scene.param_changed`` is no longer wired to the editor page
    (the signal still fires and still drives the unsaved-changes
    indicator via ``flow_scene._mark_dirty``).
  - ``_on_param_changed`` and ``_has_reactive_source`` helpers
    deleted; ``_on_run_clicked`` no longer calls
    ``self._live_timer.stop()``.
  - ``SourceNodeBase`` import dropped (was only referenced by the
    removed reactive-source check).
  Re-runs are now strictly Run-button driven. ``ImageSource``-style
  reactive sources still latch their value on streaming consumers
  when ``Flow.run()`` starts; what's gone is only the auto-trigger
  on every keystroke / spinner click.

## [0.1.41] — 2026-04-26

### Fixed
- **Spinbox up/down buttons show their arrow chevrons again.**
  Adding ``::up-button`` / ``::down-button`` geometry rules in
  0.1.37 fixed the buttons-overlap-the-value-field problem but
  also switched Qt into stylesheet-rendering mode for the
  sub-controls — without an explicit ``image`` rule on
  ``::up-arrow`` / ``::down-arrow`` Qt drops the native chevron
  drawing entirely, leaving the buttons icon-less. Two small SVG
  arrow assets (``assets/icons/spinner_up.svg`` / ``spinner_down.svg``,
  light-grey triangles) ship in the repo now and ``apply_dark_theme``
  injects their absolute paths into the QSS at apply time, with
  ``Path.as_posix()`` for cross-platform url-quoting safety.
  Adds ``::up-button:hover`` / ``::up-button:pressed`` (and the down
  variants) so the buttons get a subtle background highlight on
  mouseover and a darker pressed state — small UX touch the previous
  fully-stylesheet-styled spinbox was missing.

### Added
- ``assets/icons/spinner_up.svg`` and ``spinner_down.svg``: 7×7 px
  light-grey triangle SVGs used by the spinbox QSS rules above.
  Inline polygons, no external dependencies.

## [0.1.40] — 2026-04-26

### Changed
- **Param widgets line up along a uniform X anchor per node.**
  Previously each row's inline editor was right-aligned within the
  available space, which meant the widget's left edge floated based
  on how long the port label in front of it was — a row with
  ``file_path`` and a row with ``min`` could not look like a clean
  vertical stack because their widgets started at different X.
  ``NodeItem._layout_param_widgets`` now picks a single
  widget-start X per node (one ``WIDGET_INSET`` past the longest
  param-bearing input label) and positions every widget at that X.
  Width still varies per widget (checkbox stays at its compact
  ``minimumSizeHint``, FilePathParamWidget stretches to fill the
  row), but the left edges align. ``_compute_width`` updated to
  size the node body off the *combined* longest-label-plus-widest-
  widget-min so the uniform anchor always has room.

## [0.1.39] — 2026-04-26

### Fixed
- **Param widget height locked to a compact 22 px regardless of OS
  style.** Without an explicit ``setFixedHeight`` Qt picks
  ``sizeHint().height()``, which on native styles ranges from ~22 px
  (Fusion) to ~28 px (Windows-Vista, macOS). The same node looked
  visibly taller on those machines and rows of different widget
  kinds (QSpinBox vs QLineEdit) drifted into different heights on a
  single node body. ``ui.param_widgets`` gains a
  ``PARAM_VALUE_HEIGHT = 22`` module constant; every value-bearing
  control (the QSpinBox / QDoubleSpinBox / QLineEdit / QComboBox in
  the single-element widgets, plus the QLineEdit and Browse / View
  buttons in ``FilePathParamWidget``) gets ``setFixedHeight`` to
  that value. Layout dump after the fix: every editable widget is
  exactly 22 px tall on any platform; the QCheckBox in
  ``BoolParamWidget`` keeps its native ~15 px because checkboxes
  don't render meaningfully larger.

## [0.1.38] — 2026-04-26

### Changed
- **Internal: widget-sizing magic numbers consolidated into named
  constants.** Two cleanup passes triggered by user feedback:
  - ``ui.node_item.NodeItem`` gains a ``WIDGET_INSET = 4.0`` class
    constant for the gap between an inline param widget and the
    row's right edge / its input label. The duplicated
    ``widget_inset = 4.0`` locals in ``_compute_width`` and
    ``_layout_param_widgets`` plus the unnamed ``4.0`` in ``paint``
    all use the single class const now.
  - ``ui.port_item.PortItem`` gains ``LABEL_OFFSET = 11.0`` (was
    ``RADIUS + 6`` recomputed in three places — ``paint``,
    ``_compute_width``, ``_layout_param_widgets`` — once as
    ``label_margin`` and twice as ``port_margin``). The relationship
    between dot radius and label inset stays in the file that owns
    the dot.
  - ``ui.param_widgets`` gains module-level ``PARAM_VALUE_MIN_WIDTH``
    (96), ``PATH_LINE_EDIT_MIN_WIDTH`` (80) and
    ``PARAM_BUTTON_WIDTH`` (36). The four ``setMinimumWidth(96)``
    calls (Int / Float / String / Enum widgets), the
    ``setMinimumWidth(80)`` on the FilePath line-edit, and the two
    ``setFixedWidth(36)`` calls for the Browse / View buttons now
    reference the named constants. Tweaking the spinbox column or
    button size now happens in one spot.

## [0.1.37] — 2026-04-26

### Changed
- **Node layout: outputs at top, inputs at bottom (Blender-style).**
  Previously sockets were paired side-by-side row-for-row (input on
  the left, output on the right of the same row). Now output sockets
  stack at the top of the body right under the header (right-aligned),
  followed by all input sockets (left-aligned). Each input row may
  carry an inline param widget on its right; outputs never have
  widgets. ``_io_top`` is replaced by ``_outputs_top()`` /
  ``_inputs_top()`` and ``paint`` / ``_compute_width`` /
  ``_layout_param_widgets`` are reworked accordingly. The body grows
  taller for nodes that have both inputs and outputs (Median: 2 rows
  instead of 1; Overlay: 8 instead of 7); ``_compute_width`` simplifies
  because rows are no longer paired and the widget can extend all the
  way to the right edge of the input row.

### Fixed
- **QSpinBox / QDoubleSpinBox up/down buttons stop overlapping the
  value field.** The dark-theme stylesheet was setting ``padding:
  3px 6px`` on ``QSpinBox`` / ``QDoubleSpinBox`` without reserving
  room for the sub-controls; Qt's style engine drew the up/down
  buttons on top of the text. The stylesheet now adds an explicit
  ``padding-right: 18px`` plus ``::up-button`` / ``::down-button``
  rules that pin the buttons to the right edge with a 16-px width
  and consistent dark-theme separator border. ``::up-arrow`` /
  ``::down-arrow`` keep the native style's arrow drawing at a
  proportional 7×7 px so the icons stay legible at the new
  PORT_ROW_HEIGHT.

## [0.1.36] — 2026-04-26

### Fixed
- **Inline socket widgets no longer collapse into their own
  buttons.** Three follow-up fixes after the param-as-port layout
  introduced in 0.1.34:
  - ``PORT_ROW_HEIGHT`` 22 → 28 px so a native QSpinBox / QLineEdit
    has room to render its full-size up / down arrows and text
    caret. The previous 22 px was below the OS-style natural
    height; QSpinBox would render but with the spinner buttons
    squeezed into ~6 px of vertical space, the user-visible
    "tiny icons" report.
  - ``MAX_WIDTH`` 220 → 320 px so a node carrying a
    :class:`FilePathParamWidget` (line-edit + Browse + View
    ≈ 160 px wide) auto-fits to a width that doesn't squeeze the
    line-edit under the buttons. ``ImageSource`` ends up at ~280
    px now instead of being capped at 220 with its line-edit
    overlapping the two buttons.
  - Per-widget width logic in ``_layout_param_widgets`` switched
    from ``max(60, min(140, avail))`` to
    ``max(min_size_hint, min(size_hint, avail))``. Stretchy
    widgets (QSpinBox, QLineEdit-based FilePath) report a
    generous size hint and fill the row width; fixed-size widgets
    (a QCheckBox like ``ValueSource.loop``) report ~14 px and
    stay tucked to the right of the row instead of stretching
    across as empty whitespace.
  Width budget computation in ``_compute_width`` uses
  ``minimumSizeHint`` instead of a hardcoded 100-140 cap so the
  auto-fit gives every widget at least its non-overlapping minimum.

## [0.1.35] — 2026-04-26

### Changed
- **Param-as-port migration (step 8/8): flow file format
  finalised.** The on-disk per-node ``params`` key is renamed to
  ``port_defaults`` to reflect the post-NodeParam mental model —
  what's persisted are the literal default values each port uses
  when no upstream is connected, not "node parameters" as a
  separate concept.
  Saver writes the new key. Loader reads ``port_defaults`` first
  and falls back to ``params`` if absent, so flow files saved
  before this version still load identically; their ``params``
  shape (``{name: value, …}``) is byte-compatible with the new
  ``port_defaults``. All 15 bundled sample flow files have been
  re-saved to the new format.
- **Last lingering NodeParam reference cleared.** The ASCII layout
  diagram in ``NodeItem``'s docstring still mentioned "param rows
  (QWidget) — one label + editor per NodeParam"; rewritten to
  describe the inline-socket layout that replaced it in 0.1.34.

## [0.1.34] — 2026-04-26

### Changed
- **Param-as-port migration (step 7b/8): inline socket layout.**
  Param widgets are no longer collected in a separate property-panel
  ``QWidget`` above the IO rows; each one now sits directly on its
  input port's row, right of the port name (Blender-style). The
  ``_build_params_widget`` panel-builder is gone; ``_build_ports``
  builds a per-row ``QGraphicsProxyWidget`` for every input port
  whose metadata carries a ``"param_type"``. ``_relayout``
  positions one widget per row in ``_layout_param_widgets``,
  width-clamped between 60 and 140 px and right-aligned within the
  row so it never overlaps the input label or an output label
  sitting on the same row. ``paint()`` truncates the input label
  on widget-bearing rows so the label text never paints
  underneath the widget.
- **Preview widget (Display's pixmap) moves below the IO rows.**
  Previously stacked at the bottom of the property panel; now
  positioned in its own ``QGraphicsProxyWidget`` below all input/
  output rows where it inherits the resize grip's leftover
  vertical space exactly like before.
- **Live refresh of widget enabled/disabled state on connect/
  disconnect is intentionally not wired** (the user reported the
  previous attempt at this was too racy). Disabled state is set at
  ``NodeItem`` creation only; after a connect or disconnect the
  user re-opens the flow / clicks elsewhere to pick up the
  refreshed state.

### Removed
- Unused ``QLabel`` and ``QVBoxLayout`` imports in ``ui.node_item``.
- The ``_params_widget``, ``_proxy`` and ``_params_height``
  attributes on ``NodeItem`` (replaced by per-row ``_param_proxies_by_row``
  / ``_param_widgets_by_row`` dicts plus a single ``_preview_proxy``).

## [0.1.33] — 2026-04-26

### Removed
- **``NodeParam`` class.** The descriptor that paired a name +
  :class:`NodeParamType` + metadata dict has been deleted from
  ``core.node_base``; every consumer in the codebase now reads the
  same information directly off the matching :class:`InputPort`
  (``port.name``, ``port.metadata["param_type"]``, ``port.metadata``).
  ``NodeParamType`` is unchanged — it still lives in ``node_base``
  and still drives widget dispatch (just keyed off
  ``port.metadata["param_type"]`` now). Saved flow files load
  identically; the on-disk format is unaffected.

### Changed
- **Param-as-port migration (step 6/8): UI binds against
  ``InputPort`` directly.** ``ParamWidgetBase`` and every concrete
  param widget (``IntParamWidget``, ``FloatParamWidget``,
  ``BoolParamWidget``, ``StringParamWidget``, ``EnumParamWidget``,
  ``FilePathParamWidget``) now take an ``InputPort`` in their
  constructor instead of a ``NodeParam``. ``build_param_widget``
  dispatches on ``port.metadata["param_type"]``. ``NodeBase.params``
  keeps its public name but returns ``list[InputPort]`` filtered to
  the param-style ports (those with a ``"param_type"`` in their
  metadata) — the UI iterates the same list it always did.
- **``_apply_default_params`` simplified.** Now iterates
  ``self._inputs`` and applies each port's ``default_value`` to the
  matching attribute via the property setter; the old
  ``NodeParam``-driven branch is gone. Ports without a
  ``"param_type"`` in metadata (image-flow inputs) and ports without
  a ``default_value`` are skipped.

### Added
- **Param-as-port migration (step 7-min/8): widgets gray out when
  their socket is driven.** ``NodeItem._build_params_widget`` now
  reads ``port.upstream`` for each editable port and calls
  ``editor.setEnabled(port.upstream is None)``. Connecting a Value
  Source into a node's ``angle`` port disables that param's slider —
  the streamed value would override whatever the slider writes.
  Refresh on connect/disconnect at runtime is a follow-up; today
  the disabled state is set on NodeItem creation. The full inline-
  socket layout (widgets next to socket dots in the node body)
  comes in step 7b.

## [0.1.32] — 2026-04-26

### Changed
- **Param-as-port migration (step 5/8): every node moved to inline
  port-only declarations.** All editable inputs on every node are
  now declared via ``_add_input(InputPort(name, types,
  default_value=..., metadata={"param_type": NodeParamType.X, ...}))``
  in ``__init__``. The per-node ``params`` property override is
  gone — :class:`NodeBase` provides a default implementation that
  synthesises a :class:`NodeParam` for every input port whose
  metadata carries a ``"param_type"`` key, so the UI keeps
  rendering its widgets exactly as before. Removes ~25 redundant
  property overrides across the catalog.
  ``_apply_default_params()`` learned to apply port-default values
  even when no matching ``NodeParam`` is in ``self.params`` — the
  previous NodeParam-driven path still works for any code path
  that hands the framework an explicit list. Saved flow files
  load identically: port indices and connection paths are
  preserved everywhere.

## [0.1.31] — 2026-04-26

### Changed
- **Param-as-port pilot (step 4/8): Overlay drops its manual angle
  branch.** ``Overlay.process_impl`` no longer reads
  ``self.inputs[2].data.payload`` itself — the framework path from
  step 2 (port-driven attribute populate) plus step 3 (auto-port
  per param) covers it: ``self._angle`` is already populated with
  the streamed value before ``process_impl`` runs and restored to
  the user-set fallback after. Same external behaviour as before;
  the implementation just stopped duplicating what the framework
  now does for free. The explicit ``angle`` ``InputPort`` in
  ``__init__`` stays put so saved flows that referenced port
  index 2 keep loading unchanged. Other numeric params
  (``scale``, ``xpos``, ``ypos``, ``alpha``) get their auto-ports
  from step 3 and are immediately drivable too — so a flow like
  ``ValueSource → Overlay.scale`` produces an animated zoom with
  zero per-param code.

## [0.1.30] — 2026-04-26

### Added
- **Param-as-port groundwork (step 3/8): every NodeParam grows a
  matching ``InputPort``.** ``NodeBase._apply_default_params()`` now
  walks the node's ``params`` and, for each one without a same-named
  manual port, appends an optional ``InputPort`` to ``self._inputs``
  with the right ``IoDataType`` (SCALAR for INT/FLOAT, BOOL/STRING/
  ENUM/PATH for the matching ``NodeParamType``), the param's
  default as ``default_value`` and a copy of its ``metadata`` dict.
  Manual ports declared *before* ``_apply_default_params`` runs (e.g.
  Overlay's pre-existing ``angle`` socket) keep their position and
  configuration so saved flows referencing port indices still load
  identically.
  Combined with step 2's port-driven attribute population, every
  numeric / boolean / enum / path-typed param across the whole node
  catalog is now driveable from upstream — wire any SCALAR producer
  into Median's ``size``, Overlay's ``scale``, Math's ``op``, etc.
  No node code changed in this step.

### Changed
- **``is_skippable`` follows Blender's mute semantics.** Previously
  it required an exact 1:1 match between every input and every
  output. With the auto-created param-style ports that rule would
  have falsely demoted long-skippable nodes (Median, Shift, Dither,
  NCC) to non-skippable. The new rule mirrors Blender's mute: the
  node is skippable as long as *at least one* input/output pair
  exists with overlapping types, and ``_process_skipped`` forwards
  each output from the first type-compatible input. Param-style
  ports (SCALAR / BOOL / ENUM / PATH) don't share types with image
  outputs, so they're naturally invisible to skip detection — adding
  more of them can never break a node's skippability.

## [0.1.29] — 2026-04-26

### Added
- **Param-as-port groundwork (step 2/8): port-driven attribute
  population.** ``NodeBase.process()`` now wraps every
  ``process_impl`` call in a snapshot / populate / restore cycle:
  before the call, every connected input port's current value is
  written into ``self._<port_name>`` (going through the public
  ``@setter`` so existing validation / clamping / coercion still
  runs); after the call, the previous value is restored, so a
  streamed frame never permanently overwrites a user-set slider
  default. Skips ports without upstream data and ports whose backing
  attribute does not exist on the node, so image-flow inputs
  (read via ``self.inputs[i].data``, no ``self._image`` field) are
  unaffected. Setter rejection mid-populate rolls back partial
  writes via the snapshot, so a node never ends up half-mutated when
  a streamed value fails validation.
  No node migrates yet; Overlay's existing manual ``angle``-port
  branch keeps working unchanged. Cleanup of the manual override
  comes in step 4 once all nodes can rely on the framework path.

## [0.1.28] — 2026-04-26

### Added
- **Param-as-port groundwork (step 1/8).** First plumbing toward the
  Blender-style abstraction in which every editable property on a
  node is an :class:`InputPort`:
  - ``IoDataType`` gains ``BOOL``, ``STRING``, ``ENUM`` and ``PATH``
    so non-numeric properties (today's ``NodeParamType.BOOL`` /
    ``STRING`` / ``ENUM`` / ``FILE_PATH``) have a port type to ride
    on. Existing ``IMAGE`` / ``IMAGE_GREY`` / ``SCALAR`` / ``MATRIX``
    are unchanged.
  - ``IoData`` gains ``from_bool``, ``from_string``, ``from_enum``
    and ``from_path`` factories. Non-numeric payloads are stored as
    raw Python objects (``bool`` / ``str`` / ``Path`` / enum member
    or its int value); the ``payload`` accessor's return type widens
    from ``np.ndarray`` to ``Any`` accordingly. Image-specific call
    sites that use ``.image`` are unaffected.
  - ``InputPort`` gains a ``metadata: dict`` field with the same
    free-form contract ``NodeParam.metadata`` carries today (min /
    max / step / enum / filter / …). Constructor copies the dict so
    callers sharing a literal default can't accidentally cross-mutate
    state between port instances.
  No node migrates to the new abstraction in this step — that's the
  next stage. Existing flows load and run identically.

## [0.1.27] — 2026-04-26

### Changed
- **Sinks are no longer required.** ``Flow.run()`` previously raised
  ``RuntimeError`` when a flow had no ``SinkNodeBase`` — that
  requirement is gone. A flow whose terminal node is a ``Display``
  (whose inline preview already surfaces the result) is now a valid,
  runnable flow on its own.

### Removed
- **``ValueSink``.** The numeric-only sink existed only to satisfy
  the old "every flow needs a sink" rule; with that rule gone, it
  has no purpose. Numeric flows now end at ``Display`` directly. Any
  saved flow referencing ``nodes.sinks.value_sink.ValueSink`` will
  fail to load — none ship in this repo, so the only fallout is on
  user-side flow files (drop the ``ValueSink`` node and its incoming
  connection).

## [0.1.26] — 2026-04-26

### Added
- **`Overlay.angle` is port-drivable.** Overlay grew a third input —
  an optional ``angle`` SCALAR port. When unconnected, the literal
  ``angle`` parameter is used unchanged (existing behaviour, existing
  flows load identically). When connected, the streamed scalar
  overrides the parameter for that frame, so wiring a
  ``ValueSource(0..359)`` into it produces a full rotation per Run.
  This is the first pilot of the param-as-port mechanism — every
  numeric parameter is meant to grow a matching optional port over
  time. The literal param is **not** mutated by port traffic, so
  disconnecting the port restores the user-set angle. Saved flows
  keep their existing port indices: ``image=0``, ``overlay=1``, new
  ``angle=2``.

## [0.1.25] — 2026-04-26

### Added
- **`Math` node** — applies a binary arithmetic op (`ADD`, `SUB`, `MUL`,
  `DIV`, `MIN`, `MAX`) to two SCALAR inputs and emits a SCALAR. Numpy
  promotion rules apply (`int + int → int`, `int / int → float`); `DIV`
  uses `np.true_divide` so divide-by-zero produces `inf`/`nan` rather
  than crashing the flow. Lives in a new **Math** palette section.
- **`Clamp` node** — constrains a SCALAR stream to
  `[min_value, max_value]`. Inverted bounds are silently swapped so a
  transient UI state (typing one bound at a time) never raises.
- **`ConstantValue` source** — reactive, one-shot SCALAR source. Emits
  its `value` parameter once per run; the value latches on streaming
  consumers via the existing reactive-source mechanism, so a flow like
  `ValueSource → Math.a` + `ConstantValue → Math.b` transforms every
  streamed value by a fixed factor/offset.

## [0.1.24] — 2026-04-26

### Added
- **`ValueSource`** — new source node in the **Sources** palette section
  that emits a `SCALAR` payload per frame. Parameters: `min_value`,
  `max_value` (inclusive bounds), `multiplier` (each emitted value is
  `n * multiplier`; integer when multiplier is exactly 1.0, float
  otherwise) and `loop` (when `True`, cycles the range a bounded
  number of times so a Run still terminates without a Stop button).
- **`ValueSink`** — new sink node in the **Sinks** palette section that
  accepts `SCALAR` and `MATRIX` payloads, so a numeric-only flow
  (e.g. `ValueSource → Display → ValueSink`) can satisfy the "every
  flow needs at least one sink" rule. Exposes `latest_value` for tests
  and inspectors; logs each received payload at DEBUG level.
  *Removed in 0.1.27 once the sink requirement was dropped.*
- **Display now accepts `SCALAR` and `MATRIX`** — scalars render as
  formatted numbers in the inline preview label, matrices as a
  compact text grid via `numpy.array2string`. Image payloads keep
  their existing pixmap preview path. The frame callback now receives
  the full `IoData` envelope (was: bare `np.ndarray`) so the preview
  widget can dispatch on payload kind. Coexists with the FPS overlay
  added in 0.1.20: image payloads still get the FPS read-out drawn
  on the preview, scalars/matrices skip the overlay since the text
  preview has no image to annotate.

## [0.1.23] — 2026-04-26

### Added
- **Payload type expansion: `SCALAR` and `MATRIX`.** `IoDataType` gains
  two new kinds. `SCALAR` carries a numpy 0-d array (a single int/float)
  and `MATRIX` carries a 2-D numpy array of arbitrary dtype/shape. Both
  ride the existing `IoData` envelope, so the rest of the type
  machinery (port type-checking, fan-out, finish-propagation) keeps
  working unchanged. Helpers: `IoData.from_scalar(value)` and
  `IoData.from_matrix(arr)`. `IoData.image` stays as a back-compat
  alias for `IoData.payload`.
- **`InputPort.default_value`.** Each input port can now hold a literal
  seed value used when no upstream is connected — the storage slot for
  the future Blender-style "edit a socket inline when unconnected"
  workflow. The field is loosely typed (`object | None`) and not yet
  consumed by the executor, so existing nodes are unaffected. Exposed
  as a settable property plus `has_default` predicate.

## [0.1.22] — 2026-04-26

### Changed
- **Node List is now a tree view.** Each palette section is a
  collapsible group with the section name + node count as the parent
  and the individual nodes as children. The dock toolbar gained two
  icon buttons — *expand all* (``unfold_more``) and *collapse all*
  (``unfold_less``) — so the user can sweep every group open or
  closed in one click without clicking each disclosure triangle. The
  search box auto-expands any group that still has visible matches
  while typing, so leaves never hide behind a collapsed section.

## [0.1.21] — 2026-04-25

### Added
- **Directory Source.** New source node that emits every image file
  in a directory as a frame, in lexicographic order. Boolean
  ``include_subdirectories`` parameter controls whether nested folders
  are walked too. Accepts the same image formats as ImageSource (JPEG,
  PNG, WebP, CR2); files with unsupported extensions are skipped
  silently and files that fail to decode are logged + skipped so a
  single corrupt frame doesn't abort the run. The directory path is
  stored relative to ``INPUT_DIR`` when possible, matching the rest of
  the file/path handling in the app.

### Changed
- **``FilePathParamWidget`` learned a ``mode="directory"`` metadata
  flag** that switches the dialog to ``FileMode.Directory`` +
  ``ShowDirsOnly`` and routes the "view" button through ``is_dir()``
  / ``QDesktopServices.openUrl`` so it opens the OS file manager.
  Used by the new Directory Source today; available to any future
  folder-picking node.

### Fixed
- **Welcome page now scrolls the content column when it overflows.**
  ``.content-col`` was sitting inside a body that hides overflow, so
  once the "What's new" / Tips lists grew past the viewport the
  bottom items got clipped silently. Adds ``overflow-y: auto`` on
  ``.content-col`` plus a flat dark scrollbar that matches the
  panel palette.

## [0.1.20] — 2026-04-25

### Added
- **Eight new image-processing nodes.**
  - *Transform:* **Flip** (horizontal / vertical / both, mirroring
    OpenCV's ``flipCode`` convention), **Crop** (ROI by ``x, y,
    width, height``; out-of-bounds rectangles are clamped to the
    input), **Rotate** (free angle around the centre, with an
    ``expand`` toggle that grows the canvas to fit the rotated image
    so corners are never clipped).
  - *Processing:* **Gaussian Blur** (wraps ``cv2.GaussianBlur``;
    even ``ksize`` values are bumped up to the next odd integer like
    Median already does), **Invert** (per-channel ``255 - pixel``
    via ``cv2.bitwise_not``).
  - *Temporal:* a brand-new palette section. **Frame Difference**
    emits ``|current - previous|`` for change/motion detection;
    **Temporal Mean** and **Temporal Median** maintain a rolling
    buffer of the last *N* frames and emit the per-pixel mean /
    median each tick (median is robust against single-frame outliers
    where mean would smear them across the window). All three reset
    their state on a new flow run, and the rolling reductions also
    flush their buffer if the input shape changes mid-stream.
- **FPS read-out on the Display node.** From the second tick of a
  run onwards, the preview gets a small FPS counter rendered into a
  black rectangle in the top-left corner; the value is an
  exponential moving average (α = 0.2) over per-frame ``dt`` so it
  stays readable even with jittery sources. Always on — no toggle —
  since live timing information is the kind of thing you only ever
  notice when it's missing. The overlay only affects what the
  preview widget sees: the output port still forwards the original
  ``IoData`` so a downstream VideoSink isn't recording debug
  overlays into the file.

## [0.1.19] — 2026-04-25

### Fixed
- **Windows: ComboBox popup background.** Enum-typed node parameters
  use ``SceneAwareComboBox``, which is hosted inside a
  ``QGraphicsProxyWidget``. The popup container (a
  ``QComboBoxPrivateContainer`` QFrame around a ``QListView``) does
  not inherit ``autoFillBackground=True`` through the proxy on the
  Windows native style, so the dropdown rendered transparent over the
  scene canvas — the application stylesheet rules never landed on a
  real fill. ``SceneAwareComboBox`` now forces both the container and
  the view opaque on first popup, and pins their palettes to the same
  dark colours as the rest of the UI. Fixes #136.

## [0.1.18] — 2026-04-25

### Changed
- **Merge node uses the standard optional-port mechanism.** Its four
  quadrant inputs (``top_left``, ``top_right``, ``bottom_left``,
  ``bottom_right``) are now declared ``optional=True`` on the
  ``InputPort`` instead of being handled by a bespoke
  ``_signal_input_ready`` override. The dispatch logic in
  ``NodeBase._signal_input_ready`` (``not p.optional or p.upstream is
  not None``) already filters unconnected optional inputs out of the
  "wait on" set, so behaviour is unchanged: unconnected quadrants
  become black and never deadlock the node. The four ports now
  render as hollow dots in the UI — consistent with RGBA Join's
  alpha input, which was the first (and until now the only) user of
  the optional-port flag.

## [0.1.17] — 2026-04-24

### Added
- **Backdrops + Create Group.** Coloured rectangular frames drawn
  behind groups of nodes so dense pipelines can be annotated as
  loose chapter headings (e.g. "Colour prep", "Alpha mask"). The
  primary creation path is **Create Group**: select two or more
  nodes, then either click the new toolbar Group button (in a
  selection-only section together with V-Stack / H-Stack — the whole
  section appears when there's a multi-node selection and disappears
  again when there isn't) or right-click empty canvas → "Create
  Group". The backdrop is auto-fitted around the selection's
  bounding box with a generous padding, so frame size is correct
  the moment it's created and never has to be adjusted. Each
  backdrop carries an `X` close button in its header and a
  right-click menu for rename / colour preset / delete; the frame
  is intentionally not interactively resizable — the framed group's
  contents are expected to evolve, not the frame itself.
  **Dragging a backdrop sweeps every fully enclosed node along** —
  the framed set is snapshot at press-time, so nodes that weren't
  framed when the drag started don't get vacuumed up mid-flight.
  Persisted alongside nodes and connections in the flow file under
  a new `backdrops` entry; older flows without the field load
  unchanged.

### Changed
- ``PageBase`` gains a ``toolbar_layout_changed`` signal so a page
  can ask MainWindow to rebuild the toolbar when its
  ``page_toolbar_sections`` answer would change at runtime — used
  by the editor to add / remove the "Selection" section as the
  multi-node selection comes and goes.
- The empty-canvas right-click no longer clears the scene's
  selection — Qt's default mousePress handler used to deselect
  everything an instant before the context menu opened, which
  killed any multi-node selection right before "Create Group" could
  read it.

## [0.1.16] — 2026-04-24

### Fixed
- **`VideoSource` path handling is now consistent with every other
  file-based node.** Paths under `INPUT_DIR` are stored as bare
  relative names and resolved against `INPUT_DIR` at run time — same
  contract `ImageSource` / `FileSink` / `VideoSink` already followed.
  Previously `VideoSource` persisted the host-absolute path (breaking
  flow portability across machines) and resolved any relative value
  against the process's working directory (breaking the default
  `./input/example.mp4` unless launched from the repo root). The
  default is also bumped to `video.mp4`, a file that ships in
  `input/` — no more "file not found" on a fresh node. Fixes #145.

### Changed
- **Bundled flow files re-stamped to the current format.** All
  `*.flowjs` files under `flow/` had their `app_version` field
  refreshed (previously ranged from v0.1.10 down to a missing field
  entirely). No semantic changes — node / connection data is
  untouched; this is purely a metadata refresh so the stamped
  version doesn't lag behind the app by multiple releases.

## [0.1.15] — 2026-04-24

### Added
- **Unsaved-changes indicator** in the Node Editor's toolbar status
  widget. An amber "● Unsaved changes" row appears the moment the
  user edits a parameter, adds/removes a node or connection, toggles
  a node's skip state, or rearranges via V-Stack / H-Stack. The row
  clears on a successful save and when a flow is loaded or cleared.
  Implemented via a new `FlowScene.is_dirty` property and
  `dirty_changed(bool)` signal.
- **Python runtime version** on the toolbar status widget — a muted
  `Python X.Y.Z` line below the application version, surfacing which
  interpreter the running app is bound to. The same version plus the
  interpreter's path is logged at startup so bug reports include it
  without having to ask.
- **Reload** toolbar / menu action in the Node Editor. Re-reads the
  current flow's file from disk, discarding unsaved edits after a
  confirmation prompt. Reconstructs the path from `flow.name` the
  same way Save does; surfaces a status error if the flow has never
  been saved or the file has been removed.

### Changed
- Extracted `AppVersionStatusWidget` from `ui.page` into its own
  module `ui.app_version_status_widget` for symmetry with
  `FlowStatusWidget`. The editor's idle status view now embeds that
  widget directly instead of re-implementing the same label stack.

## [0.1.14] — 2026-04-24

### Added
- **Optional input ports.** `InputPort` gains an `optional=True` flag.
  An unconnected optional port no longer blocks the node's dispatcher;
  a *connected* optional port is waited on like a required one so
  producers that emit matching-frame aux planes (e.g. alpha) aren't
  raced. Optional ports render as a hollow outlined dot in the node
  editor so the affordance reads at a glance.
- **Per-pixel alpha support** in the `Overlay` node. When the overlay
  input carries a 4-channel BGRA image (RGBA PNG / WebP), its alpha
  plane is used as a per-pixel mask during the composite; the node's
  scalar `alpha` parameter acts as a global multiplier on top. The
  existing 3-channel path is unchanged and still uses
  `cv2.addWeighted` for speed. Closes #142.

### Changed
- **`RgbSplit` → `RgbaSplit`, `RgbJoin` → `RgbaJoin`.** The colour
  split/join nodes are now alpha-aware. `RgbaSplit` always emits four
  greyscale planes; a 3-channel BGR input gets a synthesised full-opaque
  (255) alpha plane. `RgbaJoin` takes B/G/R as required inputs and A
  as an optional fourth input, emitting BGRA when A is wired and plain
  BGR otherwise. Existing saved flows referencing the old module/class
  names are auto-remapped at load time via a legacy alias table in
  `ui/flow_io.py`.
- **`ImageSource` preserves alpha.** Still images are decoded with
  `cv2.IMREAD_UNCHANGED` instead of `IMREAD_COLOR`, so RGBA PNG/WebP
  payloads reach downstream nodes with four channels intact. Single-
  channel greyscale PNGs are promoted to BGR on load so the
  `IoDataType.IMAGE` contract (≥ 3 channels) still holds.

## [0.1.13] — 2026-04-24

### Added
- **Overlay node** (palette section *Composit*) — composites an
  overlay image onto a base image. The overlay is optionally resized
  by a `scale` factor, rotated by `angle` degrees (bounding box
  expanded so no pixels are lost), placed at `(xpos, ypos)`, and
  alpha-blended with opacity `alpha`. Parts of the overlay that fall
  outside the base are clipped; mixed greyscale/colour inputs are
  promoted to colour, otherwise the output stays greyscale.

### Fixed
- **Image Source: WebP files now show up in the file picker.** The
  name-filter string had a stray comma after `*.webp`, which Qt
  parsed as a literal glob pattern and caused the dialog to hide
  every WebP file. Docstring now lists WebP alongside JPEG/PNG/CR2.

## [0.1.12] — 2026-04-24

### Changed
- **Dither node preserves the input type.** Greyscale inputs still
  emit a single-channel binary image, but colour (BGR) inputs are now
  dithered per channel and emit a colour image of the same shape
  instead of being greyscaled first. The output port now accepts both
  `IMAGE` and `IMAGE_GREY`, which also makes the node eligible for the
  skip (pass-through) toggle.

## [0.1.11] — 2026-04-24

### Changed
- **NCC node: template is now a file-path parameter, not an input port.**
  The pattern image is loaded from disk once in `before_run` and
  converted to greyscale there if the file is colour, so the conversion
  cost is paid a single time per run rather than per frame. Existing
  flows that connected a second source into the NCC template port must
  be re-saved — the bundled `ncc`, `video_ncc` and `debug_ncc_video`
  flows are updated accordingly.

## [0.1.10] — 2026-04-24

### Added
- **Skip (pass-through) toggle on eligible nodes.** Nodes whose inputs
  and outputs match one-to-one by type now render an extra `»` button
  in the header. Clicking it bypasses `process_impl` and forwards each
  input payload straight to the matching output. Skipped nodes are
  visually distinct — grey header, strike-through title — and the
  flag round-trips through the flow file.

## [0.1.9] — 2026-04-24

### Changed
- **Log folder moved out of the user config dir.** `LOG_DIR` now resolves
  to `<app-folder>/logs/` (alongside `input/`, `output/`, `flow/`)
  instead of `~/.image-inquest/logs/`, so logs and faulthandler dumps
  stay visible next to the rest of the bundled app folders. `logs/` is
  added to `.gitignore`.

## [0.1.8] — 2026-04-24

### Added
- **Debug Params node.** A pass-through filter under the *Debug* palette
  section that declares one parameter of every supported
  `NodeParamType` (file path, int, float, string, bool, enum). Exists
  so every param-widget code path can be exercised through a single node
  during development.

## [0.1.7] — 2026-04-24

### Fixed
- **Black, unrecoverable node canvas on Windows after a per-node file
  picker dialog.** Passing the owning `QLineEdit` as parent to a native
  `QFileDialog` did not work on windows (#125).

## [0.1.6] — 2026-04-24

### Fixed
- **Unicode paths on Windows.** `cv2.imread()` silently fails on paths
  containing non-ASCII characters (e.g. `Stjörnhorn` in the repo path).
  `ImageSource` now reads image files via `np.fromfile()` +
  `cv2.imdecode()`, which goes through Python's Unicode-aware file I/O
  and handles any path correctly (#130).

## [0.1.5] — 2026-04-23

### Added
- **Screen-topology logging** in `FlowView`. The initial monitor layout
  (name, geometry, device-pixel ratio, refresh rate) is written to the
  log on startup, and every subsequent `screenAdded`, `screenRemoved`,
  `primaryScreenChanged`, window `screenChanged`, and view
  `QEvent.ScreenChangeInternal` is logged too. Groundwork for
  diagnosing render glitches that correlate with brief display
  blackouts on Linux Mint / X11 / NVIDIA setups.

## [0.1.4] — 2026-04-23

### Fixed
- **Save As** wrote the *old* flow name into the JSON because the
  in-memory rename happened only after `save_flow_to`. The handler in
  `NodeEditorPage._on_save_as_clicked` now applies the new name first
  and rolls it back if the disk write fails, so the saved file's
  `"name"` field always matches the chosen filename.
- **Mixing a one-shot source with a streaming source** into a
  multi-input filter (e.g. Image Source → NCC ← Video Source) now
  produces one output per streaming frame instead of a single result.
  `Flow.run` schedules reactive (one-shot) sources ahead of streaming
  ones, `SourceNodeBase.start` finishes reactive outputs immediately,
  and `InputPort.clear` retains data from a finished upstream so the
  latched value stays available across every downstream `process`
  call.
- **Bundled flow names** in `flow/` now match their filenames. Four
  files (`debug_error`, `debug_ncc_video`, `dither`, `rgb_dither`)
  carried stale `"name"` fields left over from earlier Save As bugs.

## [0.1.3] — 2026-04-21

### Added
- **Display node** (palette section *Output*) — pass-through node
  that renders every frame inline inside its own node body via a
  live `QLabel` preview. Drop it anywhere in the graph to watch
  frames in real time without leaving the editor.
- **Video Sink** — encodes incoming frames to a video file via
  `cv2.VideoWriter`. The writer opens lazily on the first frame (so
  dimensions are inferred from the data) and is finalised in
  `_on_finish` when the runner signals end-of-stream. Params:
  `output_path`, `fps`, `codec` (MP4V or XVID).
- **NCC** — normalised cross-correlation template matching node
  (`cv2.matchTemplate` with `TM_CCORR_NORMED`). Takes separate
  `image` and `template` greyscale inputs and emits an 8-bit score
  map; `retain_size` controls whether the match is padded back to
  the input image size (#110).
- **Resizable nodes.** Every `NodeItem` grows a diagonal grip at
  its bottom-right corner; drag to resize. Preview-bearing nodes
  honour both axes (the preview fills spare vertical space), others
  resize in width only. Sizes round-trip through `flow_io` via a
  new `"size": [w, h]` field on saved nodes.
- **`NodeParamType.STRING`** + `StringParamWidget` — line-edit
  editor that commits on `editingFinished` so validating setters
  don't raise mid-typing. Supports `placeholder` and `max_length`
  metadata.
- **Splash screen text.** The splash pixmap is overlaid with
  `APP_DISPLAY_NAME` and the current version in large type, with
  font sizes scaling to the pixmap height so the splash reads well
  at any asset resolution.

### Changed
- **Stream lifetime is no longer a payload.** `IoData.END_OF_STREAM`
  and `IoData.end_of_stream()` are gone; `InputPort` / `OutputPort`
  gain a dedicated `finish()` method plus a `finished` property that
  propagates across connections. `NodeBase._on_end_of_stream` →
  `_on_finish`. `Flow.run` signals end-of-stream centrally by
  calling `finish()` on every source output once every source's
  `start()` has returned, so a one-shot source can no longer drive
  EOS into a sibling input before the sibling has produced data.
  Sources stop emitting EOS inline; Merge reacts to `port.finished`.

### Fixed
- **Running a flow twice** no longer raises "`send() called after
  finish()`". `NodeBase.before_run()` calls `port.reset()` on every
  input and output port before dispatching to the subclass hook, so
  stale `finished` flags from the previous run don't block the new
  one.

## [pre-0.1.3] — accumulated, previously unreleased

### Added
- **Enum-typed node parameters.** `NodeParamType.ENUM` + an
  `EnumParamWidget` that renders a combo box populated from a declared
  `Enum` class, with pretty member labels. Dither uses it for its
  `method` parameter; `flow_io` serialises `Enum` values via their
  underlying `.value` so saved flows stay human-readable and
  backward-compatible (#51).
- **Live-coding auto-run.** Image-backed source nodes trigger a 300 ms
  debounced re-run of the flow on any parameter change so the viewer
  reflects edits in near real time.
- **Image Source / Video Source** nodes, in addition to the existing
  generic File Source.
- **Numba-JIT error-diffusion dither** (Floyd–Steinberg, Stucki,
  Atkinson, Burkes, Sierra, simple-X, simple-XY). Kernels are JIT-
  compiled once and cached to `__pycache__` for interactive-speed
  dithering.
- **Bayer ordered-dither** matrices (2×2, 4×4, 8×8), alongside a
  white-noise threshold method.
- **Adaptive Gaussian Threshold**, **Median**, **Normalize** filters;
  **Scale**, **Shift** transforms; **RGB Split**, **RGB Join**,
  **Grayscale** colour-space nodes.
- **Fit to window** and **Reset zoom** toolbar actions in the node
  editor.
- **Page-selector radio group** in the main toolbar: each page
  (Start, Editor) contributes its own menus and a named
  `ToolbarSection` group that MainWindow installs next to the
  selector.
- **Material-Icons**-based toolbar icons, rendered from the bundled
  TTF via a custom `QIconEngine` so they stay crisp at any size.
- **Dark theme** applied globally via a Qt style sheet + palette.
- **Splash screen** with monitor-aware placement so the main window
  opens on the same display.
- **CLI `--flow FILE`** to open a flow at startup.
- **Per-node status bar** messages (OK / fail / muted) with full-
  text tooltip for long error traces.
- **Rotating file log** at `~/.image-inquest/logs/image-inquest.log`
  (5 × 1 MB chunks).

### Changed
- The **node palette** was restructured: nodes now declare their own
  palette section via `super().__init__(..., section="…")` instead of
  being grouped by their base-class category. Built-in sections are
  Sources, Sinks, Color Spaces, Transform, Processing; user plugins
  can introduce new sections (#52).
- The **palette widget** was renamed from `PaletteWidget` to
  `NodeList` and its dock is now titled "Node List" (#52).
- The start page has a single primary **Create** action sized to
  match the main toolbar, with a material "add" icon; the duplicate
  client-area **Open** button has been removed since the toolbar
  already exposes one (#53).

### Fixed
- File-dialog browse button showing `.` instead of `…` on nodes
  with a file-path field.
- Node selection after the `QGraphicsObject` → `QGraphicsItem` +
  signal-helper refactor.
- Viewer showing nothing after a run because the end-of-stream frame
  was overwriting the cached output.
- Window-title duplication caused by Qt's automatic
  `applicationDisplayName` prefix.
- Node file-path field overlapping the browse button.

## [0.1.0] — initial development snapshot

Initial working prototype: start page, node editor with dockable
palette and viewer, flow save/load, and a minimal built-in node set
(File Source, Grayscale, File Sink).

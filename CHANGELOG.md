# Changelog

All notable changes to Stjörnhorn (repo: `image-inquest`) are tracked
in this file.

The format loosely follows [Keep a
Changelog](https://keepachangelog.com/en/1.1.0/) and the project aims
to adhere to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
once a first tagged release is cut.

## [Unreleased]

## [0.2.42] — 2026-04-29

### Fixed
- **Node Documentation dock no longer auto-resizes to its content.**
  Selecting a node with a long docstring or many parameters (e.g.
  the new ``Hodogram``) was pushing the dock taller and squashing
  the sibling Node List dock. Root cause: the summary ``QLabel``'s
  word-wrap-driven minimum height bled through ``sizeHint`` /
  ``minimumSizeHint`` to the enclosing ``QDockWidget``. Fix: wrap
  the panel body in a ``QScrollArea`` and override the panel's
  size-hint methods to fixed defaults (``280×360`` /
  ``180×80``). Long content now produces a vertical scroll bar
  inside the panel; the dock retains the user's chosen size.
  Issue: #233.

## [0.2.41] — 2026-04-29

### Added
- **Datenkrake: ``Hodogram`` renderer.** New filter that turns two
  columns of a ``DATASET`` into a particle-motion (hodogram) plot —
  the canonical seismology view for analysing P-wave / S-wave
  polarisation and back-azimuth. Generic enough for Lissajous
  figures, phase-space loops, or any pair of correlated signals.
  Architecture splits the geometry (``ParticleMotion`` — pure
  numpy / numpy.linalg, no matplotlib) from rendering
  (``HodogramRenderer`` — matplotlib Agg, Strategy pattern), so the
  PCA fit is testable in isolation and a future 3-D / animated
  variant slots in without touching the node. Parameters:
  ``x_column`` (default ``"N"`` — falls back to first column when
  not present), ``y_column`` (default ``"E"`` — falls back to
  second), ``width`` / ``height`` (default 360×360),
  ``color_by_time`` (gradient-colours each segment by its time
  index via viridis; default on), ``equal_aspect`` (force 1:1
  axis scaling so geometry reads correctly; default on),
  ``show_polarization`` (overlay the fitted PCA axis with an
  angle + linearity readout; default off so the node stays
  generic for non-seismic use). Issue: #222 (parent epic #218 —
  project Datenkrake).

## [0.2.40] — 2026-04-29

### Added
- **``PlotXY``: single-column Datasets plot against the row index.**
  A one-column ``DATASET`` (e.g. a seismic ASCII trace loaded by
  ``CsvSource`` with ``has_header=False``) now renders out of the box
  with the default settings — X axis is the sample number, Y axis is
  the only column. Multi-column behaviour is unchanged. New
  ``x_column = "_index"`` sentinel forces row-index X regardless of
  column count, useful for picking one column out of a wide Dataset
  and viewing it against position. Issue: #231.

## [0.2.39] — 2026-04-29

### Added
- **Datenkrake: ``PlotXY`` renderer.** New filter node that turns two
  columns of a ``DATASET`` into a labeled XY line plot (3-channel BGR
  image), so any ``Dataset`` flow can produce a viewer-ready picture
  without leaving the graph. Single piece of code covers waveforms,
  CV curves, diode I-V, spectra and any other "Y vs X" view —
  Datenkrake's payoff for keeping the payload generic. Parameters:
  ``x_column`` / ``y_column`` (empty → first / second columns of the
  input), ``width`` / ``height`` in pixels (≥ 64), optional ``title``,
  ``grid`` toggle. Axis labels include the column unit when the
  upstream stamps a ``df.attrs["units"]`` dict (``"V [V]"`` etc.).
  Renders off-screen via matplotlib's ``Agg`` backend and always
  closes the figure on exit, including error paths, so a
  long-running flow doesn't leak figures across frames. Adds
  ``matplotlib`` to ``requirements.txt``. Issue: #221 (parent
  epic #218 — project Datenkrake).

## [0.2.38] — 2026-04-29

### Added
- **Datenkrake: ``CsvSource`` node.** First end-to-end producer of
  the new ``DATASET`` payload. Reads any CSV (seismic export,
  instrument log, simulation output, …) into a ``pandas.DataFrame``
  and stamps the resolved file path into ``df.attrs["source_path"]``
  for downstream UI / error messages. Reactive — editing any
  parameter re-runs the flow, matching ``ImageSource``'s UX.
  Parameters: ``file_path`` (FilePathParam, INPUT_DIR-relative),
  ``delimiter`` (default ``","``; type ``\\t`` for tab),
  ``has_header`` (default True; off → synthetic ``c0``, ``c1``, …
  column names), ``decimal`` (default ``"."``; set to ``","`` for
  European decimals). Lines beginning with ``#`` are always treated
  as comments and skipped, so files that lead with a metadata header
  (seismic ASCII traces, gnuplot output, instrument logs) load
  without configuration. Issue: #220 (parent epic #218 — project
  Datenkrake). Re-lands #220 after the original PR #225 merged into
  the now-deleted feature branch instead of ``main``.

## [0.2.37] — 2026-04-29

### Added
- **Datenkrake foundation: ``IoDataType.DATASET`` payload.** New
  payload kind on the ``IoData`` envelope that carries a
  ``pandas.DataFrame``. Columns identify channels (``"time"``,
  ``"Z"``, ``"N"``, ``"E"`` for seismic; ``"V"``, ``"I"`` for diode
  I-V; etc.) and ``df.attrs`` carries free-form metadata
  (``sample_rate``, ``units``, ``station``, …). One generic payload
  kind serves every tabular domain so the same downstream nodes
  compose across them. ``IoData.from_dataset(df)`` factory rejects
  non-DataFrame input to keep the contract explicit. ``pandas`` added
  to ``requirements.txt``. Issue: #219 (parent epic #218 — project
  Datenkrake).

## [0.2.36] — 2026-04-29

### Fixed
- **Type-checker hygiene in ``core.port``.** ``IoDataType`` is now
  imported alongside ``IoData``. The annotations across ``InputPort``
  / ``OutputPort`` referenced it without an import; this worked at
  runtime because ``from __future__ import annotations`` keeps
  annotations as strings, but Pylance flagged it as unresolved.

### Removed
- **Empty ``if TYPE_CHECKING: pass`` block in ``core.port``** and the
  now-unused ``TYPE_CHECKING`` import. Leftover from an earlier
  import shape; carried no symbols.

### Repository Rules
- New CLAUDE.md guideline: opportunistic dead-code cleanup
  (empty ``TYPE_CHECKING`` blocks, unused imports, commented-out
  code, stale TODOs, leftover debug prints) is folded into whatever
  change is in flight rather than waiting to be asked.

## [0.2.35] — 2026-04-29

### Changed
- **InputPort supports multiple listeners (M11).** The legacy
  ``set_on_state_changed`` single-callback slot was a footgun:
  ``NodeBase`` wired its dispatcher there during port registration,
  but anyone else calling the same setter (debug hooks, UI
  indicators, tests) silently overwrote the dispatcher and broke
  the node's per-frame execution. Replaced with
  ``add_listener`` / ``remove_listener`` — multiple observers
  coexist on the same port without clobbering each other. Listener
  invocation iterates a snapshot of the list so a listener that
  registers another mid-fire doesn't corrupt the iteration.
  ``NodeBase._add_input`` switched to ``add_listener``.

### Migration
- Tests that called ``port.set_on_state_changed(callback)`` are
  renamed to ``port.add_listener(callback)``. The semantics for a
  single-listener port are identical; the only difference is that
  a second call no longer replaces the first.

### Resolved (refacturing backlog)
- **M11** — port single-callback slot retired in favour of a
  multi-listener registration API.

## [0.2.34] — 2026-04-29

### Added
- **Display node shows total frame count.** The top-left debug overlay
  now carries a second line — `N <count>` — showing the total number of
  frames processed since the current run started. The count is visible
  from the very first tick (unlike FPS which needs a measurable `dt`
  and only appears from tick 2). A new read-only property
  `frames_processed` exposes the same counter to tests and the UI
  without scraping the overlay text. The helper method that paints the
  overlay is renamed `_draw_overlay` (was `_draw_fps_overlay`) to
  reflect that it now carries more than FPS. Closes #207.

## [0.2.33] — 2026-04-28

### Removed
- **Legacy hand-rolled-port code paths in ``NodeBase``** (H2 PR-2f).
  The two ``setattr`` loops at the end of
  ``_apply_default_params`` (one walking ``self._inputs`` for ports
  with ``"param_type"`` metadata, the other walking
  ``self._params``) are gone. Every node in the codebase uses
  class-level descriptors after PR-2e, and descriptors write their
  defaults through the full ``__set__`` pipeline (coerce / validate
  / shape) at ``NodeBase.__init__`` time. The loops were dead code
  in production after PR-2e; this PR removes them and tightens the
  contract.

### Changed
- **Default writes go through the descriptor pipeline at
  construction time.** ``NodeBase.__init__`` previously used
  ``object.__setattr__`` to skip validation when initialising each
  descriptor's backing slot — the defaults were re-applied through
  ``setattr`` later in ``_apply_default_params``. With the legacy
  loop gone, ``__init__`` now uses ``setattr`` directly so the full
  pipeline runs once, atomically. A misconfigured default (e.g. an
  even value on an ``OddIntParam``) now fails loudly at
  construction rather than landing silently.
- **``_populate_port_driven_attributes`` gates on ``"param_type"``
  metadata** instead of the silent ``hasattr`` skip that had been
  papering over hand-rolled ports without backing attributes. The
  intent is now explicit: only param-style ports (the ones a
  descriptor auto-creates) participate in the per-frame
  populate / restore dance; image / data-flow inputs are skipped
  because the gate filters them out.

### Resolved (refacturing backlog)
- **H2** — convention-driven port↔attribute coupling — done across
  PRs #208 / #209 / #211 / #212 / #213 / #214 and this PR.
- **H3** — param-widget boilerplate — done in PR #205.
- **H4** — port-construction boilerplate — subsumed by H2.
- **M9** — parallel widget dispatch tables — subsumed by H2.
- **L13** — ``_apply_default_params`` swallowing exceptions — the
  exception-swallowing loop is gone with the rest of the legacy
  path.

## [0.2.32] — 2026-04-28

### Changed
- **Param descriptor sweep — batch 5, final node migration
  (H2 PR-2e).** Migrated the remaining nine nodes:
  - Sources: ``ConstantValue``, ``DirectorySource``,
    ``GradientSource``, ``ImageSource``, ``ValueSource``,
    ``VideoSource``.
  - Sinks: ``FileSink``, ``VideoSink``.
  - Test fixture: ``DebugParam`` (one parameter of every type, used
    to exercise the param-widget code paths during development).
  After this PR every node in the codebase uses class-level
  ``core.params`` descriptors for its parameters; zero hand-rolled
  ``_add_input(InputPort(...))`` + ``@property``/``@setter`` pairs
  for parameter ports remain anywhere under ``src/nodes/``.

### Notes
- The ``on_change=`` hook flagged in ``refacturing.txt`` H2 as an
  open question for ``ImageSource.file_path`` turned out
  unnecessary — the existing setter only normalises the path via
  ``store_relative_to(INPUT_DIR)``, and ``FilePathParam._coerce``
  already does that. The hook stays parked in the design notes in
  case a future side-effect setter actually needs it.

## [0.2.31] — 2026-04-28

### Added
- **``constant=True`` flag on the descriptor protocol.** When set,
  the descriptor doesn't auto-create an :class:`InputPort`; instead
  ``NodeBase`` appends it to ``self._params`` so the UI's existing
  inline-no-socket dispatch picks it up. The descriptor itself
  satisfies the :class:`NodeParam` read interface (``name``,
  ``metadata``, ``default_value``, ``upstream``) so no wrapper is
  needed. Threads through every concrete descriptor's
  ``__init__``.
- **``_ExpressionParam(StringParam)`` in ``Math``.** A small custom
  subclass that compiles + validates the expression atomically on
  every ``__set__``. Replaces the hand-rolled
  ``@expression.setter`` and the static-method
  ``_compile_expression`` / ``_validate_ast`` pair, both of which
  moved to module scope so the descriptor can call them. Per-frame
  evaluation still skips the parse step — the compiled bytecode
  lives on a side-slot ``_compiled`` written by the descriptor's
  ``__set__`` alongside the canonical text.

### Changed
- **Param descriptor sweep — batch 4 (H2 PR-2d).** Migrated the
  four NodeParam-using filters: ``ApplyColormap``, ``Resize``,
  ``Math`` and ``Notify``'s ``severity``. Each loses its
  hand-rolled ``_add_param(NodeParam(...))`` declaration plus
  associated ``@property``/``@setter`` pair in favour of one
  descriptor declaration with ``constant=True``. The error message
  on out-of-range enum sets shifted from the legacy
  ``"X must be one of [...]"`` to ``EnumParam``'s
  ``"X: cannot map ... to a Y member"`` — the two corresponding
  tests (``test_apply_colormap``, ``test_resize``) updated to
  match.

## [0.2.30] — 2026-04-28

### Added
- **``StringParam`` and ``FilePathParam`` descriptors.** The last
  two pieces of the H2 descriptor surface for port-style params:
  - ``StringParam`` — line-edit-backed text param with optional
    ``placeholder`` / ``max_length`` widget metadata.
  - ``FilePathParam`` — path picker with ``mode`` (open / save /
    directory), ``filter``, ``base_dir``, ``caption``. Storage
    type is ``pathlib.Path``; ``_coerce`` runs incoming values
    through ``store_relative_to(base_dir)`` so paths inside
    ``base_dir`` end up in their portable relative form (matches
    the legacy hand-rolled setter on every file-path-using
    node).

### Changed
- **Param descriptor sweep — batch 3 (H2 PR-2c).** Migrated NCC
  (full — ``template`` to ``FilePathParam`` and ``retain_size`` to
  ``BoolParam``) and Notify (partial — ``message`` to
  ``StringParam``; ``severity`` stays as a ``NodeParam`` until the
  descriptor protocol gains a ``constant=True`` flag in PR-2d).
  NCC's loaded-template-image slot was renamed
  ``self._template`` → ``self._template_image`` so it doesn't
  collide with the descriptor's ``Path`` storage on the same
  attribute name.

## [0.2.29] — 2026-04-28

### Added
- **``BoolParam``, ``EnumParam``, ``ClampedFloatParam`` descriptors;
  ``min_exclusive`` / ``max_exclusive`` flag on ``FloatParam``.**
  Four new pieces in ``core.params`` covering the descriptor types
  the next batch of filters needed:
  - ``BoolParam`` — toggle backed by ``IoDataType.BOOL``.
  - ``EnumParam`` — combo-box backed by ``IoDataType.ENUM``; coerce
    accepts the enum member, its ``.value``, or its ``.name``.
  - ``ClampedFloatParam`` — float whose ``min`` / ``max`` clamp via
    ``_shape`` rather than raise via ``_validate``. Used when
    out-of-range input is a UX choice (``Overlay.alpha`` —
    ``2.5`` becomes ``1.0``, no exception).
  - ``FloatParam(min_exclusive=True)`` / ``max_exclusive=True`` —
    strict bounds (``> min`` rather than ``>= min``). Used by
    ``Overlay.scale`` which must be strictly positive.

### Changed
- **Param descriptor sweep — batch 2 (H2 PR-2b).** Migrated six more
  filters: Overlay, Subpixel Mosaic, Flip, Dither, Rotate, Scale.
  Each loses its ``self._<name>`` init lines, hand-rolled
  ``_add_input(InputPort(...))`` constructions, and per-param
  ``@property``/``@setter`` pairs in favour of single descriptor
  declarations. ``Overlay`` is the headline migration since it
  exercises all five descriptor types in one node — including the
  new clamping float and exclusive-bound float.

## [0.2.28] — 2026-04-28

### Changed
- **Param descriptor sweep — batch 1 (H2 PR-2a).** Migrated eight
  more filters to the class-level descriptor pattern landed in
  PR-1: Median, Delay, Clamp, Shift, Temporal Mean, Temporal Median,
  Adaptive Gaussian Threshold and Crop. Each loses the
  ``self._<name>`` init line, the hand-rolled
  ``_add_input(InputPort(...))``, and the ``@property``/``@setter``
  pair in favour of a single descriptor declaration. Files are
  30–50% smaller; metadata, validation and port construction now
  live in one place per parameter.
- **Descriptor protocol: validation runs before shaping.**
  ``_ParamBase.__set__`` is now ``coerce → validate → shape`` rather
  than ``coerce → validate``. Domain subclasses override the new
  ``_shape`` hook (e.g. ``OddIntParam``'s even→odd rounding) so a
  literal value below ``min`` raises rather than being silently
  shaped up into range. Preserves the semantics of the hand-rolled
  setters this descriptor replaces — e.g. ``Median.size = 0`` still
  raises ``ValueError``.

### Deferred
- ``Overlay`` and the remaining nodes that need new descriptor
  types (Bool/String/Enum/FilePath, plus a clamping float for
  ``Overlay.alpha`` and an exclusive-bound float for
  ``Overlay.scale``) move in subsequent PRs.

## [0.2.27] — 2026-04-28

### Changed
- **Class-level node-parameter descriptors (PR-1 of 2).** Node
  parameters used to require three coupled declarations — backing
  attribute, hand-built ``InputPort``, ``@property``/``@setter`` —
  all keyed by the same name and easy to drift. The new
  ``core.params`` module ships ``IntParam``, ``OddIntParam`` and
  ``FloatParam`` descriptors that own storage, coercion, validation,
  metadata and port construction in one declaration. ``NodeBase``
  collects them via ``__init_subclass__``, initialises every private
  slot from the declared default before subclass ``__init__`` runs,
  and auto-creates each descriptor's matching ``InputPort`` in
  ``_apply_default_params`` *after* the explicit ports the subclass
  added — preserving image-first / params-second visual ordering on
  every node. ``OddIntParam`` demonstrates the OCP property: the
  even→odd kernel-size rule is named once and inherited by any
  filter that needs it, instead of being re-implemented inside each
  setter. ``GaussianBlur`` migrated as the proof (95 → 57 lines). No
  behaviour change; ``.flowjs`` save format unchanged. The remaining
  ~40 nodes migrate in PR-2, after which the legacy
  ``_add_input(InputPort(...))`` path retires. Backlog item H2 from
  ``refacturing.txt``.

### Fixed
- **Drive-by typing fix in ``core/node_base.py``.** The module
  imported ``override`` from ``typing``, which only became available
  in Python 3.12 — the rest of the codebase uses
  ``typing_extensions.override`` for 3.11 compatibility. Aligned this
  one outlier so the file imports cleanly under 3.11 (matching
  ``pyproject.toml``'s ``requires-python = ">=3.11"``).


## [0.2.26] — 2026-04-28

### Changed
- **Param-widget plumbing centralised.** The six param-editor widgets
  embedded in every node (Int, Float, Bool, String, Enum, FilePath)
  used to each repeat the same zero-margin ``QHBoxLayout`` setup and
  the same ``setMinimumWidth`` / ``setFixedHeight`` pair on their
  value control. That ritual now lives in two helpers on
  ``ParamWidgetBase`` — ``_make_row_layout()`` and
  ``_size_value_control()`` — so the layout shape is named in one
  place and any future param widget defaults to the right visual
  contract. No behaviour change. Backlog item H3 from
  ``refacturing.txt``.

## [0.2.25] — 2026-04-28

### Added
- **Settings page.** A new top-level page (toolbar selector next to
  *Log*) hosts persistent application settings. The first entry is
  *Enable debug logging*: when off (default) the rotating log file
  captures INFO and above, when on it captures the full DEBUG stream.
  The toggle is saved to ``~/.image-inquest/settings.json`` and is
  applied both at next startup and live to the currently-running file
  handler.

## [0.2.24] — 2026-04-28

### Fixed
- **Fit toolbar action now resizes the canvas, not just the
  viewport.** Previously *Fit* only called ``QGraphicsView.fitInView``
  with a fixed 40 px margin, so the underlying ``sceneRect`` was
  never touched and the layout often ended up off-center inside an
  over- or under-sized canvas. Fit now computes the node bounding
  rect, expands the ``sceneRect`` to that rect plus 5% padding on
  each side (= 10% larger overall), leaves the layout naturally
  centered in the canvas, and then zooms the view to show the whole
  canvas. Repeated clicks are idempotent (canvas doesn't grow on
  every press); an empty scene is a no-op. Tiny layouts that would
  zoom past the 5× cap are clamped to the cap *and* re-centered on
  the canvas — the previous code only reset the transform to 1:1
  and left the scroll bars wherever they happened to be, leaving
  small graphs visibly off-center. The fit rect is now computed
  from structural items only (nodes + backdrops), not from
  ``itemsBoundingRect()``. Wires are cubic Beziers whose control
  points extend the path's bounding rect beyond the straight line
  between ports; on graphs where wires curve more on one side, that
  asymmetry shifted the centre and the visible node cluster ended
  up off-centre even though the rect was technically centered.
  Issue #191.

## [0.2.23] — 2026-04-28

### Added
- **Backdrop resize grips.** Backdrops can now be resized after
  creation. Hovering or selecting a backdrop reveals eight grips
  (four corners, four edge midpoints); dragging any grip resizes
  the rectangle live, with the opposite corner / edge anchored.
  Width and height clamp at the existing
  ``MIN_BACKDROP_WIDTH`` / ``MIN_BACKDROP_HEIGHT`` so the frame
  never collapses into an unclickable sliver. Resizing changes
  only the frame's geometry — the framed nodes are never swept
  (that still requires dragging the body). Resized geometry
  round-trips through save / load like every other backdrop
  property. Issue #192.

### Changed
- **Filter documentation sweep.** Every parameter on the eighteen
  filter nodes that were still undocumented after v0.2.20 now ships
  with a ``"description"`` metadata key, and where it makes sense
  also a numeric ``min`` / ``max`` bound and a ``unit`` suffix.
  Affected nodes:
  ``AdaptiveGaussianThreshold``, ``ApplyColormap``, ``Clamp``,
  ``Crop``, ``DebugParam``, ``Delay``, ``Dither``, ``Flip``,
  ``Math``, ``Median``, ``Ncc``, ``Notify``, ``Overlay``,
  ``Scale``, ``Shift``, ``SubpixelMosaic``, ``TemporalMean``,
  ``TemporalMedian``.

  Visible effects:
  - Hovering an inline parameter widget on these nodes now shows
    the description as a tooltip (introduced in v0.2.20).
  - The Node Documentation panel (v0.2.21) renders the full
    descriptions, ranges and units in its Inputs and Parameters
    sections.
  - Numeric param widgets that gained a ``min`` / ``max`` now
    constrain the spin-box range instead of accepting and then
    rejecting out-of-range values at run time. The bounds match
    what the existing setters already enforced — e.g.
    ``Median.size >= 1``, ``Crop.width >= 1`` — so no saved flow
    stops working; the change is purely a friendlier edit
    surface.

  Lint progress: ``test_param_ports_have_description`` flips from
  18 ``XFAIL`` cases to 18 ``XPASS``; the six remaining ``XFAIL``s
  are all sources / sinks and are scoped for a follow-up sweep PR.

## [0.2.22] — 2026-04-27

### Added
- **Node-palette section state persists across sessions.** The
  expand/collapse state of every section in the node palette (Sources,
  Sinks, …) is saved to `~/.image-inquest/node_list_state.json` on app
  close and restored on the next launch. Search-driven expansion is not
  persisted — only manual toggles and the expand-all / collapse-all
  buttons are remembered. New sections default to expanded; stale keys
  for removed sections are silently ignored. Issue #190.
- **Generic per-page state persistence API in `PageBase`.** `PageBase`
  gains `save_state()` / `restore_state()` lifecycle hooks (concrete
  no-ops by default) so any page can opt into persistence without
  modifying `MainWindow`. `NodeEditorPage` overrides both to cover dock
  layout (issue #183) and palette section state (issue #190) in one
  call. `MainWindow.closeEvent` and `__init__` now loop over all pages
  rather than hardcoding the editor page.

## [0.2.21] — 2026-04-27

### Added
- **Node Documentation dock.** *(Layout follow-up: re-tuned for
  narrow docks — small fonts, compact ``<dl>`` layout instead of
  Markdown bullets, dotted module path moved off the visible meta
  line into the H1 ``title`` tooltip so the panel no longer
  forces a wide dock. Sphinx cross-reference roles
  (``:class:`Resize```, ``:func:`cv2.GaussianBlur```, …) and RST
  inline code (``` ``foo`` ```) are stripped / converted before
  rendering so the dev syntax doesn't leak into the user-facing
  text. Class docstrings are PEP-257-cleandoc'd so body
  indentation doesn't survive into HTML. ENUM-typed default
  values render as the member name (``SCALE``) instead of the raw
  ``<MyEnum.SCALE: 0>`` repr. Body content is now split between
  an always-visible *summary* (node name, section, brief
  description, **Inputs** and **Outputs**) and a collapsible
  *Details* disclosure (rest of the docstring, **Parameters**).
  Inputs and outputs are structural — the user needs them upfront
  to decide how to wire the node — so they sit in the head;
  descriptions and parameter ranges are longer-form and live
  behind the disclosure. The disclosure's open / closed state
  survives selection changes within a session, so a user reading
  docs can switch between nodes without re-clicking it. Nodes
  with nothing in their details body hide the toggle entirely
  instead of dangling an empty disclosure.)* A new ``QDockWidget`` under the Node
  List that shows full documentation for the currently selected
  node: the class docstring, every input and output port with its
  accepted types, every parameter with type / default / range / unit,
  and (for ``ENUM`` params) the integer-to-name mapping rendered as
  ``0=NAME, 1=…``. Two selection sources feed the panel:
  - **Palette click** — the new
    ``NodeList.entry_selected(NodeEntry)`` signal previews the
    docs of the class the user is about to drop.
  - **Canvas click** — selecting a node on the graph takes
    precedence and shows the docs of the class the user is
    actually configuring.
  Driven by the existing ``core.node_doc.describe_node`` introspection
  helper, so the panel automatically grows richer as the
  documentation sweep tracked under issue #187 progresses (more
  ``description`` keys → more body text in the panel). Toggle through
  the *View* menu; position and visibility persist across sessions
  via ``dock_layout.json`` like the existing docks. The Markdown
  renderer is a pure function (``ui.node_doc_panel.render_node_doc``)
  so the bulk of the rendering logic is testable without an
  ``QApplication``.

## [0.2.20] — 2026-04-27

### Changed
- **Node palette tooltips now show the class docstring instead of
  the import path.** Hovering ``Resize`` in the left-hand palette
  used to show the dev-internal string
  ``nodes.filters.resize.Resize`` — accurate but useless to a user
  deciding whether to drop the node. The tooltip now renders the
  first paragraph of the class docstring (capped at 400 chars), and
  falls back to the import path only when the class has no docstring
  yet — so the documentation sweep tracked under issue #187 has a
  visible reason to happen. ``NodeEntry`` gains a ``docstring`` field
  populated by the AST scanner, so this requires no module imports
  at scan time.

### Added
- **Parameter widgets show port descriptions on hover.** First
  user-visible consumer of the ``core.node_doc`` metadata schema
  (introduced in 0.2.19): every inline param widget — spinboxes,
  combo boxes, checkboxes, line edits, file-path rows — now surfaces
  the port's ``"description"`` metadata as a Qt tooltip on the
  widget *and* on every hover-target child, so the help text fires
  whether the user's cursor is on the wrapper or on the inner
  control. Pre-existing per-control tooltips (e.g. the path
  widget's "Open in system image viewer" eye button) are preserved.
- **Initial documentation sweep.** ``Gaussian Blur`` (ksize, sigma),
  ``Resize`` (width, height, method), ``Rotate`` (angle, expand),
  ``Image Source`` (file_path) and ``File Sink`` (output_path) gain
  ``description`` (and where appropriate ``min`` / ``unit``) entries
  on their parameter ports. Five nodes' worth of the lint test in
  ``tests/test_node_documentation.py`` flip from ``XFAIL`` to
  ``XPASS`` as a result; the rest of the corpus follows in
  subsequent thematic doc-only PRs tracked under issue #187.

## [0.2.19] — 2026-04-27

### Added
- **Node-documentation schema and introspection helper.** New
  ``core.node_doc`` module that declares the ``PortMetadata``
  ``TypedDict`` recognised in every ``InputPort.metadata`` /
  ``NodeParam.metadata``, and provides ``describe_node(cls)`` —
  a JSON-serialisable description of a node class (display name,
  section, docstring, ports, params, normalised enum mappings).
  Two consumers are intended: parameter-panel tooltips in the editor,
  and the AI flow assistant (issue #187) whose system prompt needs a
  machine-readable catalog of every available node. A companion lint
  test (``tests/test_node_documentation.py``) is currently
  ``xfail``-marked while the existing node corpus is brought up to
  spec; already-compliant nodes show up as ``XPASS`` so the sweep
  progress is visible without breaking CI. Pure additive change — no
  existing node behaviour is altered.

## [0.2.18] — 2026-04-27

### Added
- **Gradient Source: linear mode.** ``GradientSource`` gains a
  ``mode`` parameter alongside ``direction``: ``SYMMETRIC`` (the
  pre-existing centred double gradient — tilt-shift, vignette) and
  ``LINEAR`` (a one-sided 0 → 255 ramp — cross-fades, day/night
  transitions, soft-edge wipes). Defaults to ``SYMMETRIC`` so saved
  flows from 0.2.17 keep their previous output. ``band_width`` also
  works in linear mode, where it carves out a leading dead-zone
  before the ramp starts. RADIAL ignores ``mode`` — a rotation-
  symmetric "linear" radial has no meaningful interpretation, so
  the node falls back to the symmetric ramp.

## [0.2.17] — 2026-04-27

### Added
- **Masked Blend filter.** New ``MaskedBlend`` node under *Composit*
  that blends two images through a separate greyscale mask:
  ``out = base * (1 - m) + overlay * m`` with ``m = mask / 255``.
  Fills the gap left by ``Overlay``, which only supports a uniform
  alpha or a per-pixel alpha baked into a BGRA overlay's 4th channel
  — ``MaskedBlend`` accepts the mask as a separate input so any
  greyscale producer (procedural gradient, threshold output, distance
  field, hand-painted PNG) can drive the blend. Mismatched mask
  resolutions are auto-resized to the base's dimensions so a small
  procedural gradient can mask a full-resolution video stream
  without manual size matching.
- **Gradient Source.** New procedural ``GradientSource`` node under
  *Sources* that emits a single-channel ``IMAGE_GREY`` gradient
  image. Configurable direction (``VERTICAL`` / ``HORIZONTAL`` /
  ``RADIAL``), a central plateau width and a smooth-vs-linear ramp
  toggle. Reactive, so size / direction / band edits live-update the
  downstream preview. Designed as the procedural mask source for
  ``MaskedBlend`` (tilt-shift, vignette, soft compositing) without
  having to ship a pre-rendered PNG.
- **Tilt-shift sample flow.** ``flow/video_tiltshift.flowjs`` chains
  ``VideoSource`` → ``GaussianBlur`` → ``MaskedBlend`` driven by a
  vertical ``GradientSource``, producing the classic miniature-faking
  effect (sharp horizontal band, softly blurred top / bottom).

## [0.2.16] — 2026-04-27

### Added
- **Apply Colormap filter.** New ``ApplyColormap`` node under
  *Color Spaces* that colorizes a single-channel ``IMAGE_GREY`` input
  through one of eleven OpenCV palettes — VIRIDIS (default), PLASMA,
  MAGMA, INFERNO, JET, TURBO, HOT, BONE, PARULA, OCEAN, COOL —
  emitting a 3-channel BGR ``IMAGE``. Designed as the display-side
  companion to producers of greyscale fields (FFT magnitude, depth
  maps, channel splits) so visualization stays out of the producer
  node. JET is the historically common spectrogram / FFT-magnitude
  palette in MATLAB, Audacity and similar tools; TURBO is the modern
  perceptually-improved drop-in.

## [0.2.15] — 2026-04-26

### Added
- **Dock-layout presets.** New ``View → Dock Layout`` submenu with two
  one-click arrangements: *Inspector on Right (default)* and
  *Inspector under Node List* (the pre-0.2.14 layout). Qt's
  drag-and-drop into a split-with-existing-dock zone is precise enough
  to be hard to discover when the source dock is on the opposite side
  of the canvas, so both useful arrangements are exposed as menu
  entries in addition to the existing freeform drag affordances.
  Issue: #183

## [0.2.14] — 2026-04-26

### Changed
- **Output Inspector docks on the right by default.** Previously the
  Output Inspector shared the left dock area with the Node List in a
  50/50 vertical split. The inspector's content (a stack of large
  image previews) is taller than wide and benefits from a full-height
  column on its own; the Node List keeps the left, the Inspector
  takes the right, and the canvas keeps everything in between. All
  the existing Qt dock affordances (drag, float, tab, hide) are
  unchanged. Issue: #183

### Added
- **Persistent dock layout.** The editor's dock arrangement (Node
  List / Output Inspector positions, sizes, floating / tabbed state,
  visibility) is now saved on app exit and restored on the next
  launch. The layout lives under
  ``~/.image-inquest/dock_layout.json`` as a versioned base64
  wrapper around ``QMainWindow.saveState()``. Corrupt, missing, or
  wrong-version files fall back silently to the right-hand default
  so the editor always comes up in a usable state. Issue: #183

## [0.2.13] — 2026-04-26

### Fixed
- **Display preview drops 4-channel frames silently.** PNG / WebP
  images with an alpha channel never appeared in the ``Display``
  node. The per-frame BGRA → QImage conversion referenced a
  ``Format_BGRA8888`` enum that does not exist in PySide6;
  the resulting ``AttributeError`` was swallowed by a broad
  ``except`` and the frame was dropped. Now uses
  ``Format_RGBA8888`` with an explicit ``cv2.cvtColor`` channel-
  order swap. Issue: #179

### Added
- **Notifications hub** (``core/notifications.py``). Process-wide,
  Qt-free dispatch for non-fatal info / warning / error messages
  emitted by nodes or UI widgets. Subscribers receive
  ``(severity, message)`` tuples synchronously on the producer's
  thread; the editor page bridges to the UI thread via a queued
  Qt signal so the banner is safe to mutate.
- **Three-severity ``MessageBanner``.** The top-right banner used to
  cover only red errors (``ErrorBanner``); it now also handles
  amber warnings and blue info messages via ``show_warning(message)``
  / ``show_info(message)``. Wired to the notifications hub so any
  ``notifications.info(...)`` / ``notifications.warn(...)`` call
  surfaces in the UI without interrupting the running flow. The
  Display preview's frame-conversion path uses ``warn`` instead of
  the previous silent ``logger.exception``. Renamed
  ``ErrorBanner`` → ``MessageBanner`` (file, class, refs) to
  reflect the broader scope.
- **``Notify`` node** (``UI`` section). Inline image pass-through
  with ``severity`` (Info / Warning / Error) and a port-style
  ``message`` input. ``Info`` / ``Warning`` emit through the
  notifications hub (run keeps going); ``Error`` raises a
  ``RuntimeError`` (run aborts at the node). The ``message`` port
  accepts a typed-in literal or any upstream ``STRING`` source so
  the banner text can be driven dynamically per frame.

### Changed
- **``Delay`` node moved from ``Debug`` → ``UI`` section.** The node
  is genuinely useful as a "slideshow pacing" knob (one frame per
  second from a directory walker into a Display, etc.), not only
  as a development aid; the section move makes it discoverable
  from the regular palette layout.

## [0.2.12] — 2026-04-26

### Added
- **HSV / HSL split and join nodes.** Four new ``Color Spaces``
  filters: ``HSV Split``, ``HSV Join``, ``HSL Split``, ``HSL Join``.
  Decompose a BGR (or BGRA — alpha is dropped) image into three
  uint8 greyscale planes and merge them back. The full-range hue
  variant of OpenCV's converter (``cv2.COLOR_BGR2HSV_FULL`` /
  ``COLOR_BGR2HLS_FULL``) is used so the H plane spans the full
  0..255 range, keeping its greyscale preview uniformly bright.
  The ``HSL`` ports are labelled in the user-facing H, S, L order
  even though OpenCV stores the channels as H, L, S internally —
  the node re-orders before / after ``cv2.cvtColor``. Round-trip
  through split → join preserves greys exactly and stays within a
  small uint8-quantisation noise budget on arbitrary colour input
  (HSV / HLS ↔ BGR is not bit-exact at 8-bit precision).
- **2-D FFT and inverse FFT nodes.** New ``Frequency`` section with
  two filters:
  - ``FFT 2D`` — takes a single-channel (greyscale) image and
    emits two payloads: a complex ``MATRIX`` ``spectrum`` (DC
    centred via ``np.fft.fftshift``) suitable for in-place
    frequency-domain manipulation, and an 8-bit greyscale
    ``magnitude`` (``log1p`` of the spectrum, normalised to
    0..255) that can be wired straight into a ``Display`` node
    for a quick visual.
  - ``Inverse FFT 2D`` — takes the centred complex ``spectrum``
    emitted by ``FFT 2D`` (or a user-modulated copy of it) and
    reconstructs a uint8 greyscale image. The ``ifft2`` result
    is rounded before clipping so ``FFT 2D → Inverse FFT 2D``
    is a pixel-exact identity on greyscale uint8 input —
    without the explicit ``np.round``, sub-ULP float drift
    would truncate values like ``15 - 1e-13`` to ``14`` on the
    cast.
  Colour images aren't accepted directly because ``MATRIX`` is
  2-D only; split into single channels first (``RGBA Split`` /
  ``HSV Split`` / ``Grayscale``) and FFT each channel separately.

## [0.2.11] — 2026-04-26

### Fixed
- **ImageSource default file fixed.** The `file_path` default was
  `"example.jpg"`, which was never bundled under `input/` — dropping a
  fresh `ImageSource` node and pressing Run raised a `FileNotFoundError`
  immediately. Default is now `"ship.jpg"`, which ships with the
  application. A new regression test (`tests/test_default_inputs_exist.py`)
  asserts that every read-side source node's file-path default resolves to
  an existing file under `INPUT_DIR`. Issue: #173

## [0.2.10] — 2026-04-26

### Changed
- **Relative-path normalisation deduplicated.** Six file-IO nodes
  (``ImageSource``, ``VideoSource``, ``DirectorySource``,
  ``FileSink``, ``VideoSink``, ``Ncc``) used to carry their own
  copy of the same five-line "store relative when inside the
  well-known base dir, otherwise keep absolute" snippet plus a
  paired three-line resolver. Both halves now live in
  ``core/path_utils.py`` as ``store_relative_to(value, base_dir)``
  + ``resolve_against(path, base_dir)``; every setter and
  ``_resolved_path`` call through it. Behaviour is unchanged
  (covered by the existing path-normalisation and node-IO test
  suites plus a new dedicated ``tests/test_path_utils.py``).
  Issue: #174

## [0.2.9] — 2026-04-26

### Added
- **Resize node.** New ``Transform`` filter that resizes an image to
  an explicit ``(width, height)`` using one of three strategies,
  selected by the ``method`` enum:
  - ``SCALE`` — stretches the X and Y axes independently to match
    the target (aspect ratio not preserved; calls
    ``cv2.resize`` directly).
  - ``CROP_OR_FILL`` — centres the source on a target-sized canvas
    at pixel scale, cropping where the source overflows and
    padding with black where it doesn't. No resampling.
  - ``BEST_FIT`` — scales uniformly to the largest size that fits
    inside the target, centres on a black canvas (letterbox /
    pillarbox). Aspect ratio preserved.
  Greyscale (1 channel), BGR (3) and BGRA (4) inputs all
  supported; output dtype + channel count match the input. Canvas
  fill is plain ``np.zeros`` — RGB(0,0,0) for colour, alpha=0 for
  BGRA (transparent black; split / re-join the alpha channel
  separately if an opaque-black letterbox is needed).

## [0.2.8] — 2026-04-26

### Fixed
- **Param-widget focus and node selection were decoupled.** Clicking
  inside a spinbox / line-edit / combo / checkbox on a node body
  gave the *widget* keyboard focus but did not select the *node* —
  the Output Inspector kept showing whatever was selected before,
  and ``FlowScene.keyPressEvent``'s Delete-routing branch (which
  decides between deleting the selected node and forwarding the key
  to the focused widget) targeted the wrong thing once focus and
  selection drifted apart. ``NodeItem`` now installs a focus event
  filter on every embedded ``ParamWidgetBase`` and its focusable
  descendants: a ``QEvent.FocusIn`` makes the owning node the *only*
  selected item (collapsing any prior multi-selection). The inverse
  also holds — ``NodeItem.itemChange`` watches for
  ``ItemSelectedHasChanged → False`` and clears keyboard focus from
  every embedded widget that still has it, so the next keystroke
  can't edit a control whose owning node is no longer active.
  Issue: #170

## [0.2.7] — 2026-04-26

### Changed
- **Value Source: ``multiplier`` replaced with ``increment``.** The
  emitted sequence is now defined directly by step size:
  ``min_value=0, max_value=10, increment=0.5`` emits ``0, 0.5, 1.0,
  …, 10.0``. Whole-number increments keep emitted values integer
  (so a downstream Display shows ``42`` rather than ``42.0``);
  fractional increments promote every value to float. ``increment``
  must be > 0 — the setter rejects 0 / negative values rather than
  silently producing an empty / infinite range. The upper-bound
  comparison carries a small tolerance so float drift (10 * 0.1 ==
  1.0000000000000002) doesn't truncate the last value of a range
  like ``min=0, max=1, increment=0.1``. **No backward compatibility**
  with the previous ``multiplier`` param: flows saved against the old
  schema still load (the unknown ``multiplier`` key is logged and
  ignored, ``increment`` falls back to its 1.0 default), but anyone
  relying on a non-1.0 multiplier needs to manually rewrite the
  range — e.g. old ``min=-180, max=0, multiplier=2.0`` becomes new
  ``min=-360, max=0, increment=2``. The bundled
  ``flow/test_numeric.flowjs`` and ``flow/video_overlay_rot.flowjs``
  samples were updated.

## [0.2.6] — 2026-04-26

### Added
- **Streaming sources interleave frame-by-frame.** ``SourceNodeBase``
  grew an ``iter_frames()`` generator API; ``ValueSource``,
  ``VideoSource`` and ``DirectorySource`` now yield once per emitted
  frame, and ``Flow.run`` round-robins their iterators so two
  streaming sources driving two param ports on the same node both
  animate. Pre-fix, two ``ValueSource``s wired into ``Overlay.angle``
  and ``Overlay.xpos`` produced exactly one composite frame total
  (the first source drained entirely before the second sent
  anything). Param-style input ports (``param_type`` in metadata)
  also latch their last value across the dispatcher's clear, so
  when the shorter source exhausts the longer one keeps firing
  against the latched value rather than stalling.
- **Stop button on the editor toolbar.** Long-running flows
  (multi-thousand-frame video decodes, looping ``ValueSource``s)
  can now be cancelled mid-run. ``Flow.request_stop`` flips a flag
  the execution loop polls between every interleave step;
  ``FlowRunner.request_stop`` forwards the click from the UI thread
  to the worker thread (Python's GIL handles the bool write).
  ``after_run`` fires on every node on stop so video captures
  release cleanly. The action is greyed out while idle and is the
  only enabled action while a run is in flight.

### Changed
- **Dispatcher only fires on a fresh arrival.** ``InputPort`` grew
  an ``is_fresh`` flag (set by ``receive``, cleared by ``clear`` /
  ``reset``); ``NodeBase._signal_input_ready`` now requires both
  "all waited inputs have data" *and* "at least one is fresh"
  before invoking ``process``. Without it, a sibling input's
  ``finish`` would re-fire the dispatcher against latched stale
  values and emit a duplicate composite frame once param-port
  latching landed.

## [0.2.5] — 2026-04-26

### Changed
- **Overlay placement is now centre-anchored.** The Overlay node's
  `xpos` / `ypos` params (and their matching SCALAR ports) now denote
  the centre of the rotated, scaled overlay's bounding box on the
  base instead of its top-left corner. Rotation already pivoted
  around the overlay's centre, so placement and rotation now share
  the same reference point — a logo driven by a 0..360° angle ramp
  stays put instead of orbiting the anchor. Behavioural break for
  existing flows: an old `xpos=0, ypos=0` placement now centres the
  overlay at the base's top-left corner; bump those numbers by half
  the overlay's rendered width / height to recover the previous look.
  The bundled `flow/video_overlay.flowjs` and
  `flow/video_overlay_rot.flowjs` samples were updated accordingly.

## [0.2.4] — 2026-04-26

### Fixed
- **Frozen bundle was missing the `input/`, `output/`, and `logs/`
  per-user directories on first launch, and the sample input images
  shipped in the dev tree weren't bundled at all.** File dialogs
  defaulted to non-existent paths and there was nothing to load. The
  PyInstaller spec now bundles `input/` and `flow/` as data, and
  `main._seed_user_data()` runs at startup to (a) `mkdir(exist_ok=True)`
  every user-data directory and (b) copy the bundled sample images and
  flows into the user dir on first launch. Idempotent — only seeds
  files that aren't already present, so anything the user saves
  persists across launches. Issue: #165

## [0.2.3] — 2026-04-26

### Fixed
- **Frozen bundle couldn't load any flow.** The PyInstaller spec used
  `collect_submodules('nodes')` to enumerate the dynamically-imported
  built-in node modules, but `nodes/` and its `filters/` / `sources/` /
  `sinks/` subdirectories are PEP 420 namespace packages (no
  `__init__.py`), and `pkgutil.iter_modules` — which `collect_submodules`
  walks under the hood — silently skips namespace-package children of
  namespace packages, so the resulting hidden-imports list contained
  only the top-level `nodes` name. None of the node modules' bytecode
  ended up in the bundle, and `flow_io._instantiate_node`'s runtime
  `importlib.import_module("nodes.filters.dither")` calls all failed
  with `ModuleNotFoundError`. The spec now walks `src/nodes/` directly
  to enumerate every module name, and adds `src/` to its own `sys.path`
  so the unrelated `collect_submodules('core'/'ui'/'ocvl')` calls also
  resolve from a `src/` layout. Issue: #163

## [0.2.2] — 2026-04-26

### Fixed
- **Windows windowed bundle crashed at startup with `RuntimeError:
  sys.stderr is None`.** PyInstaller's `console=False` Windows bootloader
  leaves `sys.stdout` and `sys.stderr` as `None`, which broke
  `faulthandler.enable(file=sys.stderr, ...)` at import time before
  anything else could run. `src/main.py` now redirects either stream
  to `os.devnull` if it's missing; `setup_logging` continues to re-point
  faulthandler at the real log file once `LOG_DIR` is known. Linux
  AppImage was unaffected. Issue: #161

## [0.2.1] — 2026-04-26

### Added
- **PyInstaller-based binary distribution.** A new `release.yml` workflow
  triggers on `v*` tag pushes, runs a PyInstaller build on
  `windows-latest` + `ubuntu-latest`, packages the Linux bundle as an
  AppImage and the Windows bundle as a zip, and attaches both to the
  GitHub Release. End users no longer need a Python toolchain to run
  the app. Issue: #157
- **`pyproject.toml`** with the project's dependency set and a
  `stjornhorn` console entry point, so `pip install -e .` followed by
  `stjornhorn` works for developers.
- **`stjornhorn.spec`** declares the data files (assets, doc, built-in
  node sources) and dynamic-import surface (every `nodes.*`, `core.*`,
  `ui.*`, `ocvl.*` submodule) PyInstaller's static analysis can't see
  on its own.

### Changed
- **Frozen-bundle path resolution.** `src/constants.py` now
  distinguishes read-only resources (resolved against `sys._MEIPASS`
  inside a PyInstaller bundle, the repo root in dev mode) from
  writable directories — saved flows, logs, the default input/output
  folders — which move to a per-user data directory
  (`~/.local/share/Stjornhorn` on Linux, `%LOCALAPPDATA%/Stjornhorn`
  on Windows) when frozen so the app can write to them. Dev-mode
  behaviour is unchanged.

## [0.2.0] — 2026-04-26

Major release: completes the Blender-style "every editable property
is a socket" migration and the inline-widget UI rebuild. Subsumes the
0.1.18 .. 0.1.48 increments below — they're kept in this file as a
detailed implementation log of the migration steps.

### Headline changes

- **Param-as-port migration complete.** ``NodeParam`` as a separate
  class is gone; every node declares its editable inputs directly as
  :class:`~core.port.InputPort` objects with type / default / metadata
  in ``__init__``. ``IoDataType`` covers SCALAR / MATRIX / BOOL /
  STRING / ENUM / PATH alongside the original IMAGE / IMAGE_GREY,
  so any value-bearing producer can drive any matching param port
  per frame. ``NodeBase.process()`` wraps every ``process_impl`` in a
  populate / restore cycle so a node's ``self._<port_name>``
  attribute carries the streamed value during the call and the user-
  set fallback before / after — disconnecting a port reliably leaves
  the slider value the user committed in place.
- **New numeric node set.** ``ValueSource``, ``ConstantValue``,
  ``Math``, ``Clamp``. ``Display`` accepts SCALAR and MATRIX payloads
  alongside images, so a numeric flow can terminate at a Display
  without a downstream sink.
- **Sinks are no longer required.** ``Flow.run()`` accepts any flow
  with at least one source. ``ValueSink`` (which existed only to
  satisfy the old gate) is removed.
- **Inline socket UI (Blender-style layout).** Output sockets stack
  at the top of the node body, input sockets follow with their inline
  param widgets sharing a uniform left X and the right node edge.
  Resize-grip drags grow widgets along with the node; the lower
  bound is the per-node natural width so nothing spills past the
  body. The separate property-panel block above the IO rows is gone.
- **Widget rendering across OS styles.** Spinbox up/down arrows,
  combobox chevrons and checkbox glyphs ship as SVG assets in
  ``assets/icons/`` and are injected into the QSS at theme-apply
  time. Every value-bearing control locks at a compact 22 px tall.
  Wrappers paint transparent so the node body colour shows through.
  Unconnected port dots are filled black until something connects.
- **Live-preview auto-run removed.** Editing a param no longer
  triggers a flow run — re-runs are strictly Run-button driven.
- **Flow file format.** Per-node ``"params"`` JSON key renamed to
  ``"port_defaults"`` to match the post-NodeParam mental model.
  The legacy ``"params"`` key is still accepted by the loader for
  flows saved before this version.

For a step-by-step implementation log, see the 0.1.18 .. 0.1.48
entries below.

## [0.1.48] — 2026-04-26

### Fixed
- **Param widget wrapper paints transparently.** The
  ``ParamWidgetBase`` ``QWidget`` that hosts each row's
  ``QHBoxLayout`` was inheriting the global ``QWidget {
  background-color: #262629; }`` rule and painting a dark-grey strip
  behind every child — most visible as a grey rectangle around a
  ``QCheckBox`` (a 14-px box on a 24-px-tall row leaves wrapper
  background showing on three sides). ``ParamWidgetBase.__init__``
  now sets ``WA_TranslucentBackground`` so the wrapper itself
  doesn't paint a fill; the inner controls (QSpinBox, QLineEdit,
  QComboBox, FilePathParamWidget's line-edit + buttons) keep their
  own ``#1f1f22`` input-field background. Setting
  ``setStyleSheet("background: transparent")`` was tried first but
  rejected — QSS propagates to descendants, which would have
  stripped the input-field fill from the value-bearing controls
  too.

## [0.1.47] — 2026-04-26

### Fixed
- **Resize grip can't shrink a node past its content width.** The
  user-width override in ``NodeItem._relayout`` was previously
  clamped at the global ``MIN_WIDTH = 120``. For any node whose
  natural width is larger than that — Image Source's file-path
  picker is ~230, Overlay's slider rows ~159 — dragging the resize
  grip narrower past the natural floor would let the inline param
  widgets spill past the node's right edge because the widget's
  ``minimumSizeHint`` is preserved while the body shrinks. The
  lower bound is now the per-node ``_compute_width()`` result, so
  the grip can't take the body smaller than the content needs.
  Widening still works up to ``MAX_USER_WIDTH``. Smoke check:
  trying ``user_width=50`` on Image Source still renders at the
  natural 230 px; the widget's right edge sits at ``226`` (= node
  width − ``WIDGET_INSET``) at every legitimate resize.

## [0.1.46] — 2026-04-26

### Changed
- **Param widgets are right-anchored to the node edge.**
  ``NodeItem._layout_param_widgets`` previously clamped each widget
  to ``min(minimumSizeHint, sizeHint, avail)`` — the natural
  ``sizeHint`` was an upper cap, which meant dragging the resize
  grip wider only grew widgets up to that cap and then left ragged
  right edges (each widget stopping at a different X depending on
  its own ``sizeHint``). The cap is gone: widgets now span from the
  uniform left anchor (one ``WIDGET_INSET`` past the longest
  param-bearing input label) all the way to ``width - WIDGET_INSET``,
  so they grow with the node and every widget's right edge sits
  flush at the same column. Smoke check: at node widths 250 / 400 /
  600 px every Overlay slider widget reports ``x_right`` of
  245 / 395 / 595, matching the resized node.

## [0.1.45] — 2026-04-26

### Changed
- **Unconnected ports paint black inside.** Previously a required
  port was solid in its kind colour (blue for inputs, yellow for
  outputs) the moment the node was created — visually identical
  whether or not anything was actually connected. Now the fill
  tracks connection state: black when ``self._links`` is empty,
  kind colour once a link lands. Optional ports keep their bright
  outline ring (set on the pen at construction time) so the
  "OK to leave unconnected" affordance remains readable on top of
  the new black fill. ``add_link`` / ``remove_link`` call
  ``_apply_default_brush`` so the dot updates immediately when the
  user drags or deletes a link.
- ``PortItem._is_optional`` is no longer the brush dispatch axis —
  it's only consulted for the pen colour at construction. Brush is
  driven by the new ``_is_connected`` helper.

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

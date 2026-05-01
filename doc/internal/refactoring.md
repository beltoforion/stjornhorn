# Refactoring backlog

Living punch list of architectural / SOLID / code-quality issues
worth addressing. Maintained by Claude Code. New findings are
appended (or inserted into the right severity bucket); resolved
items are marked **DONE** with the date and the PR/commit that
closed them rather than deleted, so the history of what shifted is
recoverable.

Status markers:

- **OPEN** — not started
- **WIP** — work in progress on a branch
- **DONE** — landed on main; references PR/commit
- **WITHDRAWN** — reconsidered, no longer pursued (with reason)

**Last reviewed:** 2026-05-01 (dynamic input ports on Math /
JoinDatasets / Mosaic via `core.dynamic_ports.DynamicInputGroup`;
new connection-listener and ports-changed framework hooks).

## High

### OPEN — H7. Subgraph / composite-node primitive (blocks multi-rate flows)

Tracked as issue **#268** — promoted to *high priority* by the user.

The push-only round-robin runner can't express nested loops, so
"for each outer frame, run an inner sweep, collect, emit one
result per outer frame" patterns must be hard-coded inside a
single `process_impl` (current `DirectionalProjection.n_angles`,
any future windowed-sweep / parameter-sweep / multi-pass node).
This is the planned-but-not-built `Subgraphs / composite nodes`
entry in `doc/internal/dataflow.md`.

Concretely missing: re-entrant `Flow.run_to_completion`,
restartable sources, `PortInputSource` / `PortOutputSink` proxy
nodes, a `Subgraph` node class, flowjs schema extension for nested
graphs, UI navigation into subgraphs, Stop-propagation through
nested flows.

**Direction:** see issue #268 for the staged PR breakdown
(framework-only first, then proxy nodes, then persistence, then
UI, then Stop hook, then demo flow). Resolves the multi-rate and
sub-graph strain points in `dataflow.md` simultaneously.

### OPEN — H1. NodeBase is a god class

SRP / OCP. `src/core/node_base.py:113-536` mixes push-dispatch
(`_signal_input_ready`), freshness/optional gating, observer
plumbing, name-reflected port↔attribute bridge
(`_populate_port_driven_attributes`), skip pass-through, and run
lifecycle.

**Direction:** extract `PortDispatcher`, `PortAttributeBridge`,
`SkipStrategy`; leave `NodeBase` as data shape + abstract
`process_impl`.

### OPEN — H5. NodeItem is a 1065-line god class

SRP. `src/ui/node_item.py:336-1065` does layout, painting, geometry,
child-handle ownership, focus management, port building, widget
building, preview embedding, label truncation. `_compute_width`
(737-806) and `_layout_param_widgets` (1007-1065) duplicate
label-width logic. `_CloseButtonItem` / `_SkipButtonItem` (176-333)
are near-identical.

**Direction:** split `NodeLayout` / `NodeChrome` / `NodeBuilder`;
introduce a `HeaderButtonItem` base.

### OPEN — H6. flow_io.py reaches deep into UI types via getattr on port names

Hidden coupling. `src/ui/flow_io.py:66-69` does
`getattr(node, p.name, None)` — same convention-coupling as H2.
Also touches `item.user_size`, `item.body_height`,
`link.src_port.node_item.node` — a UI-layer module assembling
canonical persistence.

**Direction:** a `FlowSnapshot` DTO from the model + a thin scene
overlay (positions, sizes, backdrops).

## Medium

### OPEN — M7. Module-level mutable `_process_observer` is global

`src/core/node_base.py:21-34` — two simultaneous flows clobber each
other's observers.

**Direction:** per-Flow / per-run observer threaded via context,
not a module attribute.

### OPEN — M8. `_process_skipped` hard-codes type-matching policy

OCP. `src/core/node_base.py:460-480` — "first input whose
`accepted_types & out.emits`" is fixed; e.g. RgbaSplit with three
outputs cannot override.

**Direction:** strategy or overridable
`_skip_match(out) -> InputPort | None`.

### OPEN — M10. NodeEditorPage mixes page-shell with run orchestration & threading

SRP. `src/ui/node_editor_page.py:580-720` assembles `QThread`,
`FlowRunner`, signal chains, status messages, viewer auto-pick
(`_best_viewer_node`).

**Direction:** a `FlowRunController` `QObject` owning thread/runner
lifecycle and exposing started / finished / failed signals; page
becomes a thin observer.

### OPEN — M12. `FlowScene.connect_ports` mixes raise-on-error with return-None

ISP / leaky. `src/ui/flow_scene.py:205-232` raises `TypeError` on
incompatible ports but returns `None` for "trivial" rejections —
callers must both `try`/`except` *and* check `None`.

**Direction:** a `Result` / dedicated error enum, or always raise.

### WIP — M13. Sinks combine write-to-disk with clock-cardinality

SRP. `src/nodes/sinks/file_sink.py:24` declares a second `tick`
SCALAR input alongside `image`; the sink uses it to decide *how
many times* to write. That mixes two concerns: writing a frame
(sink) and pulse-rating the writes off an upstream clock
(cardinality / lifecycle). Same shape will recur on `VideoSink`
and any future sink the moment animation flows need it.

The cleaner pattern is what filters already do today: a SCALAR
clock plugged into a port-driven param drives the filter's
lifecycle, the filter emits one frame per tick, and the sink just
writes whatever arrives. The TickTack umbrella's `IoMeta`
(`src/core/io_data.py:36`) is now an open-ended `str → Any`
mapping — perfect substrate for letting filters tag their SCALAR
inputs into outgoing meta so sink filename templates
(`out_$tick:2$.png`) keep working without a sink-side port.

**Direction:**

1. Convention: a filter with a SCALAR input port stamps that
   port's current value into outgoing `IoMeta` under the port
   name (`Shift` → `meta["offset_x"] = 37`). Last-writer-wins
   along a chain. Always stamp (default + connected alike) so
   tokens don't silently disappear when ports are unwired.
2. Reserve framework-meta keys (`frame_index`, `source_path`,
   `timestamp`) — port-name validator rejects collisions.
3. Drop the `tick` input port on `FileSink` (and any future
   sink that grows one). Sink cardinality = upstream image
   stream cardinality.
4. New `Repeat` node — `(image, clock) →
   image_with_meta_stamp` — for the "fire the same image N
   times" case where there's no upstream filter to clock.
   Replaces every sink-side tick port across the codebase.

**Trigger:** TickTack Step 4 / #246 (animated hodogram) needs
filter-level meta tagging anyway; folding this in early avoids
hardcoding sink-port cardinality semantics that Step 4 would
then have to undo.

**References:** umbrella #249, FileSink port surface
`src/nodes/sinks/file_sink.py:24`, `IoMeta` schema notes in
`src/core/io_data.py:36`, demo flow `flow/test_ranged.flowjs`.

## Low

### OPEN — L14. Magic numbers in NodeItem layout outside the constants block

`src/ui/node_item.py:358-391` defines a clean block, but `100.0`
(preview min height, line 947) and `2`/`4` paddings in
`boundingRect` (line 501) are inline. Pull to the same constants
block.

### OPEN — L15. `FlowScene.keyPressEvent` uses `isinstance(focusItem(), QGraphicsProxyWidget)` to detect "user is typing"

Leaky / fragile. `src/ui/flow_scene.py:558` — couples scene-level
key dispatch to a Qt implementation detail.

**Direction:** a focus-policy delegate or an explicit "edit mode"
flag from `NodeItem`.

## Resolved

### DONE — PolarSpectrum was a too-special monolith

Resolved 2026-05-01 on branch `claude/refactor-polar-spectrum-node-SuRec`.

The original `PolarSpectrum` node fused three distinct concerns
(directional projection of a 2-component vector signal, per-column
1-D magnitude FFT, polar heatmap rendering) and was therefore only
useful in exactly one downstream shape. Replaced by three
single-responsibility nodes:

- `DirectionalProjection` (filter, "Data") — 2-component DATASET →
  N-column DATASET with `r_j = x·cos θ_j + y·sin θ_j`. Stamps
  `df.attrs["thetas_rad"]` for downstream binding.
- `Spectrum` (filter, "Frequency") — per-column magnitude FFT with
  optional Hann taper, dB scaling, and `freq_max` clipping. First
  1-D FFT node in the catalogue (complementary to `Fft2D`).
- `PolarHeatmap` (filter, "Visualization") — generic polar (θ, r)
  heatmap renderer for DATASET payloads.

The old chain reproduces as `DirectionalProjection → Spectrum →
PolarHeatmap`; bundled demo flow updated in the same PR.

### DONE — H2. Convention-driven port↔attribute coupling via name reflection

Resolved 2026-04-28 across PRs #208, #209, #211, #212, #213, #214,
and PR-2f.

- **PR-1 (#208)** — landed `core.params` with `_ParamBase` +
  `IntParam` + `OddIntParam` + `FloatParam`; descriptor-aware
  `NodeBase`; `GaussianBlur` as proof.
- **PR-2a (#209)** — sweep batch 1 (8 numeric-only filters).
- **PR-2b (#211)** — added `BoolParam`, `EnumParam`,
  `ClampedFloatParam`, `FloatParam(min/max_exclusive)`; migrated
  Overlay + 5 more.
- **PR-2c (#212)** — added `StringParam`, `FilePathParam`
  (Path-typed with `base_dir`-aware coerce); migrated NCC +
  Notify.message.
- **PR-2d (#213)** — added `constant=True` flag; migrated Apply
  Colormap, Resize, Math (with custom `_ExpressionParam`),
  Notify.severity.
- **PR-2e (#214)** — migrated all 6 sources, both sinks, and
  `DebugParam`. Zero hand-rolled `NodeParam` / param-style
  `InputPort` remains in `src/nodes/`.
- **PR-2f** — retired the legacy `setattr` loops in
  `_apply_default_params` and tightened
  `_populate_port_driven_attributes` to gate on `"param_type" in
  port.metadata` (replacing the silent `hasattr`-skip). Defaults
  now flow exclusively through the descriptor's `__set__`
  pipeline at `NodeBase.__init__` time.

The `on_change=` hook flagged as an open question turned out
unnecessary in practice. Design notes parked in CHANGELOG / PR-2e
PR description in case a future side-effect setter actually wants
it.

### DONE — H3. Param-widget subclasses duplicate >90% boilerplate

Resolved 2026-04-28 in PR #205. Scope was reduced after
design-review pushback — a full template-method base would have
been over-engineering. Landed two small helpers on
`ParamWidgetBase` (`_make_row_layout`, `_size_value_control`) that
every widget calls instead of inlining the QHBoxLayout dance.
`_on_value_changed` and the `int()` / `float()` / `bool()` /
`str()` coercions stay inline per subclass.

### DONE — H4. Identical port-construction boilerplate in ~35 filter files

Resolved 2026-04-28 — subsumed by H2. The descriptor *is* the port
factory; class-level declarations replace the per-node hand-rolled
`InputPort` metadata blocks.

### DONE — M9. Two parallel widget dispatch tables

Resolved 2026-04-28 — subsumed by H2. The descriptor's optional
`WIDGET_CLASS` hint lets a domain subclass (`OddIntParam`,
`ClampedFloatParam`, …) ship its own widget without growing
`IntParamWidget` / the per-`NodeParamType` registry. Adding a new
widget for a new descriptor is now a self-contained change.

### DONE — L13. `_apply_default_params` swallows every exception with debug log

Resolved 2026-04-28 in PR-2f — the loop that ran `setattr` against
hand-rolled port defaults is gone, taking the broad
`except Exception` branch with it. Default writes go through the
descriptor's `__set__` at `__init__` time; a bad default fails
loudly at construction now rather than silently logging and
carrying on.

### DONE — M11. `Port.set_on_state_changed` is a single-callback slot

Resolved 2026-04-28 — replaced the single-slot setter with
`add_listener` / `remove_listener`. `NodeBase._add_input` switched
to `add_listener`; tests bulk-renamed `set_on_state_changed` →
`add_listener` (call-site semantics are identical for a
single-listener port). New `tests/test_port_listeners.py` locks
down the multi-listener contract: registration order, the "external
observer doesn't clobber the dispatcher" footgun fix,
`remove_listener` idempotence, and snapshot-iteration so a listener
that registers another listener mid-fire doesn't corrupt the loop.
Listener ordering (dispatcher-first means observers see post-clear
state) is left for a follow-up if a real use case shows up; nothing
in the codebase depends on observers reading data between receive
and the dispatcher's clear.

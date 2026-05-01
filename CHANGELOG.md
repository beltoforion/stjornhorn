# Changelog

All notable changes to Stjörnhorn (repo: `image-inquest`) are tracked
in this file.

The format loosely follows [Keep a
Changelog](https://keepachangelog.com/en/1.1.0/) and the project aims
to adhere to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
once a first tagged release is cut.

## [Unreleased]

## [0.3.0] — 2026-04-29

### Changed (PolarSpectrum split into reusable building blocks)

- **`PolarSpectrum` removed** in favour of three single-responsibility
  nodes that compose to the same chain and stay useful on their own:
  - **`DirectionalProjection`** (section "Data"): `DATASET (x, y) →
    DATASET` with `n_angles` columns, each `r_j(t) = x·cos θ_j +
    y·sin θ_j`. Stamps the per-column azimuth array onto
    `df.attrs["thetas_rad"]` so downstream renderers can recover the
    angle binding without reparsing column names.
  - **`Spectrum`** (section "Frequency"): per-column magnitude FFT of
    a `DATASET`. The output's row index is frequency in Hz; columns
    match the input. `sample_rate`, `freq_max`, `db_scale`, and an
    optional Hann taper are configurable. First 1-D FFT node in the
    catalogue (complementary to the existing image-domain `Fft2D`).
  - **`PolarHeatmap`** (section "Visualization"): generic polar
    heatmap renderer for `DATASET` payloads. Treats columns as angle
    bins (read from `df.attrs["thetas_rad"]` or parsed from
    degree-suffixed column names) and the index as the radial axis.
    Configurable colormap, θ-zero location, and θ direction (CW for
    geographic / seismic convention, CCW for math convention).
- The original directional-FFT polar plot is reproduced by chaining
  `DirectionalProjection → Spectrum → PolarHeatmap`. Bundled demo
  flow `flow/data_display_time_series_merged.flowjs` is updated to
  the new chain in the same PR.
- Each new node has its own focused test module. The pure-math tests
  that previously lived on `PolarSpectrum._compute_spectrum` /
  `_to_db` carry over to `Spectrum`; the rotation math is now its
  own test module (`test_directional_projection`).

### Changed (PlotXY / PlotSeries config-only params)

- **`title`, `grid`, `width`, and `height` on `PlotXY` and
  `PlotSeries` are now constant params** — config-only inline editors
  instead of wireable input ports. None of these get meaningfully
  animated frame-to-frame in any reasonable flow, so the socket dots
  were just visual noise.

### Removed (PlotSeries.start)

- **`PlotSeries.start` parameter dropped.** Time-axis offsets belong
  in a dedicated transform node upstream (e.g. a Shift on the time
  column) — baking them into PlotSeries' rendering conflated config
  with data. The synthetic time axis is now ``i * step``; the band
  meta-conversion drops the offset term too. Bundled flow files
  stripped of the now-unused ``"start"`` port-default key.

### Removed (PlotXY band ports)

- **`PlotXY` lost its `band_start` / `band_end` SCALAR input ports.**
  They were a hold-over from before PlotSeries took its own cv2-overlay
  band path; nothing in-tree wires them anymore. The band-drawing code
  (`axvspan`) is gone with them. Direct PlotXY users who want a band
  can either layer it themselves on the emitted image or revisit
  introducing a band primitive when a real consumer exists.

### Fixed (PlotSeries cache invariant)

- **PlotSeries now holds a reference to its cached DataFrame** so
  CPython can't recycle the GC'd address for the next emit's
  DataFrame — that would have faked a cache hit on logically-different
  content. Surfaced by a regression test that creates throwaway
  DataFrames in a tight loop and asserts re-render count.

### Changed (PlotSeries: multi-channel stacked panels)

- **`PlotSeries` now plots every column of the input dataset as its
  own panel, stacked top-to-bottom with a shared X (time) axis.** The
  N-vs-E waveform pair previously needed two `PlotSeries` nodes; one
  node with a 2-column input (e.g. from `JoinDatasets`) now produces
  the same visual. Single-column inputs collapse to one panel and
  render exactly like before.
- **`y_column` (single) → `y_columns` (comma-separated list).** Empty
  plots every column (the `JoinDatasets` case); ``"N,E"`` filters to
  those columns; a typo loudly raises `KeyError` rather than silently
  dropping a series. Bundled flow files updated to the new key.
- The internal dependency on `AddIndexColumn` is gone — PlotSeries
  computes the synthetic time axis inline so its single-responsibility
  surface (one node = one stacked time-series plot) reads cleaner.
- The band overlay still tracks the moving window; it now spans every
  panel of the stack so the highlighted region lines up across
  channels.

### Added (merged time-series demo flow)

- **New `flow/data_display_time_series_merged.flowjs`.** A leaner
  variant of the animated-hodogram demo: both N and E channels merge
  into a single multi-column DATASET via `JoinDatasets`, a single
  `SlidingWindow` slices it per tick, and a single `PlotSeries` plots
  N and E as stacked panels with a shared time axis and moving band.
  A `PlotXY` adds the windowed N-vs-E motion plot alongside.
  **10 nodes / 10 connections** (vs 11 / 13 in the original
  multi-panel `data_display_time_series.flowjs`). The original stays
  bundled for the dedicated `Hodogram` (time-coloured trajectory +
  polarisation overlay).
- `SlidingWindow` regression-tested on multi-column DataFrames so the
  merged-channel pattern is covered by CI rather than living
  implicitly in the demo.

### Removed (RangeSource.loop)

- **`RangeSource.loop` parameter dropped.** The bounded-cycle counter
  (10 repeats when `loop=True`) was a footgun — a tick-driven flow that
  needs more frames is better expressed by widening `max_value` /
  shrinking `increment`, not by silently multiplying the run by 10×.
  The `_LOOP_CYCLES` constant is gone with it. Bundled flow files
  stripped of the now-unrecognised `"loop"` port-default key.

### Changed (window bounds via IoMeta, demo-flow simplification)

- **`SlidingWindow` carries window bounds in `IoMeta`** instead of as
  separate SCALAR outputs. Both emitted DATASETs (``dataset_windowed``
  and the new ``dataset_full`` passthrough) carry ``window_start`` and
  ``window_end`` keys on their meta. Drops two SCALAR outputs from
  SlidingWindow's port list and matches the M13 auto-stamp idiom —
  per-frame annotations ride along with the payload, not on a sibling
  channel.
- **`SlidingWindow.dataset_windowed`** (formerly ``dataset``) is the
  per-tick slice; ``dataset_full`` is the unmodified input DataFrame
  re-stamped each tick with the current window bounds. Lets
  ``PlotSeries`` plot the full trace and overlay a moving band from a
  single wire — no fan-out from the upstream `CsvSource`. The
  passthrough wraps the *same* DataFrame reference each tick so
  PlotSeries' identity-based trace cache stays warm.
- **`PlotSeries` reads band bounds from input meta** instead of from
  dedicated SCALAR input ports. The ``band_start`` / ``band_end``
  ports are gone; downstream interpretation is "if the input dataset's
  meta carries `window_start` / `window_end`, render a band".
- `PlotXY` keeps its explicit ``band_start`` / ``band_end`` SCALAR
  ports for direct uses where the band x-coords aren't sample-row
  indices on a synthesised time axis.
- **Demo flow simplified.** `flow/data_display_time_series.flowjs`
  drops 4 connections (was 17, now 13): each `CsvSource` has one
  downstream wire (its `SlidingWindow`); `SlidingWindow` fans out to
  `Hodogram` (slice) and `PlotSeries` (passthrough with band meta).
- PlotSeries' cache key now uses ``id(io.payload)`` (the DataFrame
  identity) rather than ``id(io)`` (the IoData wrapper) so the
  passthrough's per-tick ``IoData.clone`` doesn't bust the cache.

### Performance (PlotSeries trace cache)

- **`PlotSeries` caches the matplotlib trace render across ticks.**
  Keyed on the input `IoData` identity plus the visual params; an
  upstream node that emits a fresh dataset per tick (shift, resample,
  any animated filter) naturally invalidates the cache, while a held
  one-shot input (the typical `CsvSource → PlotSeries` shape) lets the
  trace render exactly once. The moving band overlay runs in cv2
  against the cached bitmap rather than triggering a fresh
  matplotlib figure. Animated-hodogram demo: ~0.9ms/tick for the band
  overlay (down from ~50ms+ for a full matplotlib redraw).
- `PlotXY.render_with_axes` exposes the underlying axes pixel/data
  geometry so downstream cv2 overlays can map data coordinates to
  image pixels without re-running the layout.

### Added (TickTack Step 4, animated hodogram, #246)

- **New `SlidingWindow` filter (section "Data").** Slices a DATASET
  into a sliding window driven by a SCALAR clock — each tick on
  ``window_index`` re-emits the slice
  ``df.iloc[start + idx*step : start + idx*step + window_size]``,
  plus the slice's ``window_start`` and ``window_end`` sample
  indices on two SCALAR outputs. The ``dataset`` input holds across
  ticks (``hold_last``) so a one-shot upstream (``CsvSource`` →
  ``SlidingWindow``) survives the streaming clock.
- **`PlotXY` and `PlotSeries` band overlay.** Two new optional
  SCALAR inputs (``band_start`` / ``band_end``); when both are
  connected, the plot renders a translucent vertical band across
  that x-range. ``PlotXY`` interprets endpoints in x-axis data
  coordinates; ``PlotSeries`` interprets them in sample-row
  coordinates and converts via its own ``step`` / ``start`` to
  the synthesised time axis — wires straight from
  ``SlidingWindow.window_start`` / ``window_end``. Band-off
  rendering is bit-for-bit identical to the pre-feature baseline.
- **`flow/data_display_time_series.flowjs` is now an animated
  flow.** Inserts ``RangeSource → SlidingWindow_{N,E} → Hodogram``
  for the windowed motion plot, wires the window endpoints into
  the ``PlotSeries`` band ports so the highlighted band sweeps
  along both waveforms in lock-step, and replaces the static
  ``FileSink`` with ``VideoSink``. Existing static-plot use cases
  stay reachable by leaving the ``window_index`` port unwired —
  reusable nodes, no replacement of the still-image variant
  needed.

### Added (source node header badges)

- **Source nodes now show a play-triangle icon (►) in their header**
  so they are visually distinct from filters and sinks at a glance,
  independent of the existing header colour.
- **Tick-count badge in the source node header.** Nodes whose frame
  count is deterministic at configuration time show it right-aligned
  before the close button (e.g. `100×` for a `RangeSource` with 100
  steps). The badge updates live as constant params are edited.
  Supported: `RangeSource` (computed from min/max/increment/loop),
  `ImageSource`, `GradientSource`, `CsvSource`, `ConstantValue` (all
  show `1×`), `VideoSource` (probes `cv2.CAP_PROP_FRAME_COUNT` once
  per file — cached by `(path, mtime)` — and caps by `max_num_frames`
  when set). `DirectorySource` shows no badge (count is not known
  until run time).
- `SourceNodeBase` gains a `tick_count() -> int | None` method;
  subclasses override it to report their frame count.
- **`NodeBase.on_flow_loaded()` lifecycle hook.** Fires once per node
  after a flow has been deserialized (params restored, scene populated,
  connections wired). Default is a no-op; `VideoSource` and
  `DirectorySource` override it to warm their tick-count caches at
  load time so the first repaint doesn't stall on `cv2.VideoCapture`
  metadata reads or directory walks. Exceptions are logged and
  swallowed by the loader so a single bad node can't sink the load.

### Changed (M13: SCALAR-port auto-stamp; sinks lose tick port)

- **`OutputPort.send` auto-stamps every SCALAR input on the owning
  node into outgoing `IoMeta` under the port name.** A filter with
  a `tick` SCALAR input emits frames with `meta["tick"] = <value>`
  for free; downstream sinks read `$tick$` from meta the same way
  they read `$frame_index$` or `$source_stem$`. Falls back to the
  port's inline `default_value` when no upstream is connected (None
  defaults are skipped).
- **`FileSink` lost its `tick` input port.** Cardinality control
  moves upstream to the new `Pulse` node — or to any filter with a
  SCALAR-driven port. The sink stays single-input: one frame in,
  one file out. The `_scalar_inputs_as_context` and `_merged_meta`
  helpers are gone too; the templating engine reads everything
  from one source now.
- **New `Pulse` filter.** Pairs a held payload (any type) with a
  SCALAR clock; each tick re-emits the held data with `meta["tick"]`
  auto-stamped. Replaces the canonical
  `RangeSource → FileSink.tick` wiring with
  `RangeSource → Pulse.tick` + `image → Pulse.data → FileSink`.
- **Reserved meta keys** (`frame_index`, `source_path`, `timestamp`)
  are now rejected at port-declaration time — a node trying to
  declare an input with one of those names raises immediately
  instead of silently shadowing the framework stamp.
- Bundled `flow/test_ranged.flowjs` migrated to the new shape:
  `ImageSource → Pulse → FileSink`, `RangeSource → Pulse.tick`,
  template `out_$tick:2$.png`.

### Changed

- **Doc panel: single-body layout.** The "Details" disclosure
  toggle is gone — the rest of the docstring and the Parameters
  table now sit inline right after the brief description, in the
  same scrollable body as Inputs and Outputs. With docstrings
  shortened across the node corpus there's nothing left worth
  hiding behind a click. The pure-function renderer collapses to a
  single ``render_node_html`` (replacing the previous summary /
  details split + ``has_details`` check), and the widget hosts one
  ``QTextBrowser`` instead of a ``QLabel`` + toggle + browser stack.

### Docs

- Swept every node docstring rendered in the Doc panel: dropped
  stale "even values are bumped" claims (the odd-only spin box now
  prevents typing an even value in the first place), removed
  implementation-detail leaks (``Wraps cv2.X``, OCVL port
  histories, numba/JIT internals, OpenCV constant names), and
  shortened the verbose entries (FFT2D, MaskedBlend, Mosaic,
  Overlay, Hodogram, PlotXY, sources). User-facing param
  descriptions kept; internal "why" rationales pruned where they
  belonged in commit messages or the refactoring backlog rather
  than the node panel.

### Fixed (#259)

- `OddIntParam` editors (`GaussianBlur.ksize`, `Median.size`,
  `AdaptiveGaussianThreshold.block_size`) now use a dedicated
  odd-only spin box: arrows step in twos, typed even values are
  rejected, and a committed even number is fixed up to the next
  odd integer on focus loss. Previously the generic `IntParamWidget`
  was used, so the spinner stopped at every integer and even input
  was silently bumped on the node while the widget kept showing the
  even value (UI ↔ model desync).
- The previously-documented `WIDGET_CLASS` hook on `_ParamBase` was
  never wired and would have required `core` to import from `ui`.
  Replaced with a string `widget_kind` metadata key consulted by
  `build_param_widget` before the per-`NodeParamType` dispatch, so
  shape-specific descriptors can opt into custom widgets without
  breaking the layering.
- `IntParamWidget` now forwards the descriptor's declared `min` /
  `max` to the spin box's `setRange`, so out-of-range values can no
  longer be typed in (the historic wide fallback is kept when no
  bound is declared). `FloatParamWidget` already did this — the
  parity gap was the same root cause that allowed e.g. negative
  kernel sizes and window=1 to hit the descriptor's validator
  instead of being refused at the widget level.
- `GaussianBlur.ksize` and `Median.size` now require `min=3` (a 1-px
  kernel is the no-op identity); `TemporalMedian.window` and
  `TemporalMean.window` now require `min=2` (a window of 1 is
  pass-through). Bundled demo flows are unaffected (none use the
  old lower bound).

### Added (TickTack Step 3, #159)

- **Filename templating** for `FileSink` and `VideoSink`. The
  `output_path` parameter is now a template with `$token$`
  placeholders that resolve at write time against the incoming
  frame's `IoMeta` (and a per-sink context for SCALAR inputs).
  Supported tokens: `$frame_index$`, `$source_stem$`,
  `$source_name$`, `$source_ext$`, plus any custom meta key any
  upstream node stamps. Width syntax `$tok:N$` zero-pads numerics
  (e.g. `out_$frame_index:4$.png` → `out_0042.png`). Templates
  with no placeholders behave as the legacy literal path.
- **`FileSink` second input** — a new optional SCALAR `tick` port
  declared after `image`. When connected, every tick drives one
  write so a streaming counter can paginate the output (e.g.
  `RangeSource(1..10) → FileSink.tick` writes ten files); when
  dangling, the legacy single-write-on-image-arrival behaviour is
  preserved. The `image` input is now `hold_last=True` so a
  one-shot source (an `ImageSource`, a `CsvSource`) survives across
  the tick stream.
- **Scalar-input-as-template-token** — every connected SCALAR input
  on a sink is exposed in the templating context under its port
  name. So a `tick` port driven by `RangeSource(1..10)` gives you
  `$tick$` → 1, 2, …, 10 in the filename, distinct from
  `$frame_index$` which is the per-port emit counter.
- New `core.filename_template.expand` helper — pure-function
  expander, fully unit-tested.
- **Template field UX** in the editor: `FilePathParamWidget` (the
  line edit on every `output_path` / `file_path` field) gained
  (a) a hover tooltip listing every available `$token$` with a
  short example, and (b) a floating live-preview popup that
  surfaces below the line edit while a template is being typed.
  The preview renders the template against a synthetic example
  context (`source_path=example/photo.jpg`, `frame_index=0`, plus
  `1` for any SCALAR input port on the node, e.g. `$tick$` when a
  tick port is wired). Hidden when the field contains no `$` so
  literal-path users see no noise. The popup is a top-level
  tooltip-style window so it never overlaps the next param row in
  the node body — the inline-label first attempt did, since
  `_layout_param_widgets` allocates a fixed row height per param.
- Bundled demo: `flow/test_ranged.flowjs` is rewired as
  `ImageSource → FileSink` with a `RangeSource(1..10) → tick` clock
  and `output_path = out_$tick:2$.png`. Running it produces ten
  files `out_01.png` … `out_10.png` from a single image source.

### Added (TickTack Step 2, #251)

- `InputPort` gains a `hold_last: bool` constructor flag. Held inputs
  retain their last received value across `clear()` and across the
  upstream's `finish()`, and the owning node's dispatcher excludes
  held ports from the "all inputs finished → propagate" rule. Lets a
  one-shot source (an image, a CSV-derived DataFrame) sit alongside a
  streaming counter without going stale or pulling the consumer down
  with it. Default behaviour for `hold_last=False` is unchanged.
- Held input ports render with a dashed PORT_INPUT_COLOR ring in the
  node editor so flows are visually self-documenting (the dot says
  "this is a held parameter, not a per-tick clock").

### Changed

- **Play Gate** (TickTack Step 1) now buffers frames in an **unbounded
  FIFO** instead of the original latest-wins single slot. Each click
  on the Play button steps through the buffered frames in arrival
  order, so a `RangeSource(0..99) → PlayGate → …` flow can be walked
  frame by frame instead of collapsing to one click. No silent drops
  — the user is responsible for keeping the feeding stream
  reasonable (a debug aid: piping a long video straight in costs
  real memory).
- **Play Gate** preview widget: the click handler no longer
  pre-disables the Play button. With the FIFO queue, the gate's
  state callback fires only on the empty ↔ non-empty transition;
  pre-disabling stranded the user with a still-non-empty queue and
  a permanently dim button after a single click.
- **Play Gate** drains its queue immediately when the user toggles
  the node into skip mode (header dimmer). Without the drain,
  pre-skip backlog stayed buffered while new frames already
  pass-through via the standard skip-node mechanism — exactly the
  inverse of what the toggle visually promises.

### Added (framework)

- New `NodeBase._on_skipped_changed(skipped: bool)` hook fires on
  every transition of the `skipped` flag. Default no-op; subclasses
  override to react (PlayGate uses it to flush its queue).
- **Meta Inspector**: the body widget now word-wraps long values
  (notably `source_path`), uses an updated placeholder
  ("(run the flow to see meta)") and forces an explicit
  `update()` after each text refresh so the proxy widget repaints
  reliably even when the callback chain runs entirely on the UI
  thread (e.g. when triggered by a Play Gate click after the run
  has otherwise quiesced).

### Added (TickTack Step 1, #250)

- Per-frame metadata on `IoData`: new `IoMeta` open-ended `str → Any`
  bag (no fixed schema — any node may stamp any key). Travels
  alongside the payload and survives pass-through filters via the new
  `IoData.clone(*, payload=..., **meta_changes)` helper. Conventional
  keys: `frame_index`, `source_path`, `timestamp`. Foundation for
  filename templating (#159) and the animated hodogram pipeline
  (#246, #251).
- The previous `IoData.with_image` was replaced by `IoData.clone(payload=...)`
  — the operation was always a clone with the payload swapped. Meta
  updates take the same method: `data.clone(frame_index=5)`, both can
  combine: `data.clone(payload=arr, frame_index=5)`. Node-author code
  that called `with_image` must switch to `clone(payload=...)`.
- `OutputPort.send` auto-stamps `meta.frame_index` from a per-port
  emit counter; `OutputPort.reset` rewinds the counter at the start
  of every flow run. Producers no longer thread frame indices
  manually.
- `ImageSource` and `CsvSource` now stamp `meta.source_path` with the
  resolved absolute path on every emit.
- New **Meta Inspector** node under the **Debug** section: pass-through
  probe that surfaces every frame's `IoMeta` (plus payload kind /
  shape) in its node body. Type-agnostic, can sit anywhere in a flow.
- New **Play Gate** node under the **Debug** section: pass-through
  with a Play button in its node body. Holds the most recent input
  frame, releases it downstream on click. Useful for stepping through
  a stream while iterating on flow design.

### Changed

- `APP_NAME` aligned with the brand: now `"Stjörnhorn"` (was the legacy
  `"Image-Inquest"`). Affects the Qt application name and the startup
  log line; user-visible captions are unchanged because they already
  use `APP_DISPLAY_NAME`, which read `"Stjörnhorn"` before.
- Renamed `ValueSource` → `RangeSource` (display name "Range Source",
  module `nodes.sources.range_source`). The node generates a bounded
  range, not a single value — the new name reflects what it does.
  Bundled flows (`flow/test_numeric.flowjs`,
  `flow/video_overlay_rot.flowjs`) updated. Existing user-saved
  `.flowjs` files referencing `ValueSource` will need to be rebuilt
  (no migration shim per repo policy).

### Versioning reset

The 0.2.x line — 98 micro-bumps tracking individual PRs — has been
retired with this slate. Going forward, ``APP_VERSION`` is a
four-component string ``Major.Minor.Release.Build``:

- The trailing **build** digit ticks once per PR for traceability.
- New **CHANGELOG** sections and welcome.html "What's new" blocks
  only appear when ``M.m.r`` moves; every build under ``0.3.0``
  collects under this section.
- The user-facing version (welcome banner, "What's new" heading)
  shows ``M.m.r`` only and drops the build digit.

The 0.2.x history is preserved in git but no longer rendered in this
file or the offline welcome page.

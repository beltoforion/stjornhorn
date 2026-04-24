# Changelog

All notable changes to Stjörnhorn (repo: `image-inquest`) are tracked
in this file.

The format loosely follows [Keep a
Changelog](https://keepachangelog.com/en/1.1.0/) and the project aims
to adhere to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
once a first tagged release is cut.

## [Unreleased]

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

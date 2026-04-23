# Changelog

All notable changes to Stjörnhorn (repo: `image-inquest`) are tracked
in this file.

The format loosely follows [Keep a
Changelog](https://keepachangelog.com/en/1.1.0/) and the project aims
to adhere to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
once a first tagged release is cut.

## [Unreleased]

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

# Changelog

All notable changes to Sparklehoof (repo: `image-inquest`) are tracked
in this file.

The format loosely follows [Keep a
Changelog](https://keepachangelog.com/en/1.1.0/) and the project aims
to adhere to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
once a first tagged release is cut.

## [Unreleased]

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

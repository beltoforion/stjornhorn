# Documentation guidelines

Living recap of the user's directives for the public-facing
documentation under `doc/`. Update this file whenever the user
gives a new doc-related instruction so the rules stay in one
discoverable place.

Audience of `doc/index.html` and `doc/welcome.html`: **end users
of Stjörnhorn**, not developers or contributors. Internal /
architectural documentation lives under `doc/internal/`.

## Style and content

- **Write for end users.** Do not document Python class names,
  method signatures, decorators, lifecycle hooks, source-code
  paths or any other implementation detail in the public docs.
  `core.params._ParamBase`, `IntParam`, `process_impl`,
  `IoData.from_*`, `core.filename_template.expand` and similar
  identifiers belong in `doc/internal/`, not `doc/index.html`.
- Refer to data types by their **legend label** (Image, Image
  (grey), Scalar, Matrix, Dataset, Bool, String, Enum, Path),
  not by enum names like `IoDataType.IMAGE_GREY`.
- Refer to parameter widgets by what the user sees ("integer
  spin box", "drop-down", "path picker"), not by descriptor
  classes (`IntParam`, `EnumParam`, `FilePathParam`).

## Per-node sections

- Each node has its own dedicated section in the node reference,
  rendered with the `.node` block style. **Do not** use the old
  `.node-grid` / `.node-card` mini-card layout — there is too
  much content per node for cards to stay readable.
- Every node section follows the same structure:
  1. `<h3 id="node-...">` with the human-readable node name.
  2. One or two paragraphs of plain prose describing what the
     node does and the typical use case.
  3. **Inputs** sub-heading listing each input port: name, data
     type label, and any role notes (required, optional, latched).
     Combine with **Outputs** as **Inputs / Outputs** when the
     node is type-preserving and has the same port name on both
     sides.
  4. **Outputs** sub-heading listing each output port the same way.
  5. **Parameters** sub-heading listing each parameter with its
     meaning and any range or units.
  6. Optionally: a closing paragraph for metadata stamping or
     other behavioural notes.
- Apply the `.node.source` / `.node.filter` / `.node.sink` /
  `.node.output` modifier so the left-edge stripe matches the
  node kind.

## Generic concept sections

- The `Node anatomy` section explains nodes in user terms:
  output ports, input ports, parameters, port-style vs constant
  parameters, source/filter/sink colour stripe. It links to
  the editor's port-legend section rather than repeating the
  legend itself.
- The port-legend screenshot (`doc/images/node_editor_legend.png`)
  belongs in the `Node editor` section under a "Port legend"
  sub-heading, alongside the description of how connections work.
  Display it via the `figure.screenshot.legend` class so it
  renders at roughly its on-canvas size, not at full content
  width.
- The `Frame metadata` section lists every metadata key the user
  is expected to encounter — `frame_index`, `source_path`, the
  scalar-port auto-stamp rule, plus dataset attribute conventions
  (`units`, `sample_rate`, `thetas_rad`). It is anchored on what
  appears in the *Meta Inspector* node and what users can type
  into File Sink filename templates.
- Concept sections must stay user-facing: no `process()`,
  `clear()`, `_signal_input_ready` etc.

## Diagrams

- Use inline SVG (no external assets) to illustrate the
  execution model and other dataflow concepts. Keep the SVGs
  simple, themed to match the page (panel-fill rectangles with
  coloured stripes for source/filter/sink/output, grey
  arrowheads).
- Wrap each SVG in a `<figure class="diagram">` with a
  `<figcaption>`. The accompanying CSS lives in
  `doc/index.html`.
- Cover at minimum: a linear flow, a multi-input node, a
  fan-out, and a streaming clock with a held input.

## Repository links and version

- Include a link to the GitHub repository
  (`https://github.com/beltoforion/stjornhorn`) in both the
  sidebar and the page footer.
- Keep the version stamps in the brand line, hero `<h1>`, and
  footer in sync with the current `M.m.r` from
  `src/constants.py` (the build digit is not displayed).

## Branding

- Both `doc/welcome.html` and `doc/index.html` carry a clickable
  `images/site_logo.webp` linking to `https://beltoforion.de`
  (`target="_blank" rel="noopener noreferrer"`).
- Layout: `header.hero` is a flex row, `align-items: center`,
  with two children — a `.hero-text` block on the left (title,
  tagline, and on welcome the `.links` button row) and the
  `.site-logo-link` on the right. The `<img>` uses a fixed
  pixel height (96 px on welcome, 80 px on index) chosen to
  visually span caption + subcaption (+ buttons on welcome).
  Do **not** try `height: 100%` / `align-self: stretch` /
  `aspect-ratio` tricks to compute the height from the text
  column — they produce circular sizing loops in
  QtWebEngine/Chromium and the logo blows up to its
  intrinsic 660×652. If the rows ever change height,
  re-tune the pixel value rather than reintroducing the
  stretch logic.

## Footers / Impressum

- Both `doc/welcome.html` and `doc/index.html` have a
  `footer.page-foot` at the bottom of the content column with
  an **Impressum** link to
  `https://beltoforion.de/de/contact/`
  (`target="_blank" rel="noopener noreferrer"`). On
  `index.html` it joins the existing repo/source links; on
  `welcome.html` it's the sole footer entry.

## `welcome.html`

- A row of button-style links (`a.button` inside `.links`)
  sits inside the hero header, immediately under the tagline,
  pointing at the hosted documentation
  (`https://beltoforion.de/stjornhorn/index.html`), the GitHub repository,
  the Issues tracker
  (`https://github.com/beltoforion/stjornhorn/issues`) and the
  Releases page
  (`https://github.com/beltoforion/stjornhorn/releases`). Open
  in a new tab (`target="_blank" rel="noopener"`).
- Do **not** put a "Offline welcome page — shown because the
  online start page could not be reached" footer at the bottom.
  The page is the welcome page in its own right; that
  fallback caption was removed.

## When in doubt

- If a piece of information is genuinely useful to a user
  (palette section names, parameter ranges, what colour a
  port shows on the canvas, what a filename token expands to),
  it belongs in `doc/index.html`.
- If it is only useful to someone reading or extending the
  source (descriptor class names, dispatcher internals,
  refactoring history), it belongs in `doc/internal/`.

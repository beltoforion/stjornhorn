# Dataflow architecture

This document describes how data flows through a Stjörnhorn flow at
runtime. It is a reference, not a tutorial — it captures the
mechanics so that framework extensions land in the right place
rather than as one-off bolt-ons.

Audience: maintainers and Claude Code. End-user docs live elsewhere
(`doc/welcome.html`, `doc/index.html`).

## Execution model: push-based, fire-and-forget

Every node has typed input and output ports. Data moves between
nodes via direct, synchronous calls:

```
OutputPort.send(IoData)
    ↓ for every connected input
InputPort.receive(IoData)
    ↓ notify_listeners()
NodeBase._signal_input_ready()      ← the dispatcher
    ↓ if all required inputs have data + at least one is fresh
NodeBase.process()
    ↓ (may be skipped — see below)
process_impl()      ← subclass logic
    ↓
OutputPort.send(IoData)             ← next hop
```

There is **no backpressure**, **no async** and **no queueing** at
the framework level. `send()` returns when every connected
`receive()` has returned. A producer never blocks waiting for a
consumer to be ready.

### Two source flavours

`SourceNodeBase` subclasses come in two flavours, distinguished by
the `is_reactive` property:

- **Reactive sources** (`is_reactive=True`) — emit once per run.
  Used for one-shot artefacts: a single image (`ImageSource`), a
  CSV-loaded DataFrame (`CsvSource`), a constant value
  (`ConstantValue`). The editor auto-runs the flow whenever any
  parameter changes so the user gets a live preview.
- **Streaming sources** (`is_reactive=False`, the default) — drive
  the flow via a per-frame generator: `iter_frames()` yields once
  per emitted frame. The runner round-robins all streaming sources
  so two clocks driving the same downstream consumer advance
  together.

`Flow.run` runs reactive sources first, then enters the round-robin
streaming loop until every source's generator raises
`StopIteration` (or the user clicks Stop).

### Threading

- `Flow.run` executes on a `QThread`-backed `FlowRunner` worker.
- Source `iter_frames` and the synchronous push chain (downstream
  `process_impl` calls) all run on that worker.
- UI hooks (preview-widget callbacks, button click handlers) hop
  back to the main thread via queued Qt signals.
- The reactive phase of `Flow.run` also runs on the worker, so a
  reactive source's emission propagates through the same
  same-thread dispatcher chain.

## Core types

### `IoData` and `IoMeta`

`IoData` is an envelope around a payload + a typed discriminator
(`IoDataType`). Payloads are payload-kind-specific:

- `IMAGE` / `IMAGE_GREY` — `numpy.ndarray`
- `SCALAR` — 0-d `numpy.ndarray`
- `MATRIX` — 2-d `numpy.ndarray`
- `DATASET` — `pandas.DataFrame`
- `BOOL` / `STRING` / `ENUM` / `PATH` — raw Python objects
  (used by param-style ports — see below)

`IoData.meta` is an `IoMeta` open-ended `Mapping[str, Any]` bag.
**No fixed schema**; conventional keys:

- `frame_index` — per-port emit counter, auto-stamped by
  `OutputPort.send`. Resets on `OutputPort.reset` at the start of
  every run.
- `source_path` — set by source nodes that read from disk
  (ImageSource, CsvSource).
- `timestamp` — run start time, populated by the runner (planned).

Custom nodes are free to add domain keys. Sinks doing filename
templating (#159) read meta to render placeholders without reaching
back through the graph.

`IoData.clone(*, payload=..., **meta_changes)` is the canonical
helper for pass-through filters: keeps the type, swaps the payload,
overrides selected meta keys. Filters that build their output from
scratch (`IoData.from_*(...)`) lose source-side meta — opportunistic
conversion to `clone` is on the refactoring backlog.

### Ports

`InputPort(name, accepted_types, *, optional=False, default_value=...,
metadata=..., hold_last=False)` and `OutputPort(name, emits)`.

Connection compatibility: an output's `emits` set must intersect an
input's `accepted_types` set. An input has at most one upstream;
fan-in is not supported. An output has any number of downstreams
(fan-out).

## The dispatcher

`NodeBase._signal_input_ready` is registered as a listener on every
input port the node owns. It runs on every input state change
(`receive` or `finish`) and decides whether to fire `process()`:

1. Compute the *waited* set: required inputs, plus any optional
   input that currently has an upstream connected.
2. If every waited input has data **and** at least one is *fresh*
   (received since the last clear), call `process()` which
   dispatches to `process_impl()` and then `clear()`s every input.
3. Otherwise, if every *clock* input (= waited inputs that aren't
   `hold_last`) has finished, call `_on_finish()` — default
   forwards `finish()` to every output.

The freshness gate matters because a `clear()` flips
`is_fresh=False` but can retain the data (see "Port-level
extensions" below). Without freshness, a sibling input's `finish()`
notification would re-fire the dispatcher against latched stale
values and emit a duplicate composite frame.

## Port-level extensions

Several behaviours that aren't pure pass-through bolt onto ports
rather than living in the dispatcher. Listed in roughly the order
they accumulated.

### Param-style ports (`metadata["param_type"]`)

Every editable knob on a node — slider, dropdown, file picker — is
modelled as an `InputPort` with `param_type` in its `metadata`. The
editor renders an inline widget whose value seeds `default_value`;
an upstream connection overrides the inline value.

Param-style ports retain their *data* across `clear()` so two
streaming sources driving two param ports on the same node can
advance round-robin without one port going dark while the other
ticks. Once the upstream finishes, the latched value persists for
the rest of the run.

Generated by `core.params._ParamBase` descriptors at
class-definition time; subclass `__init__` calls
`_apply_default_params()` once after registering its image-flow
ports.

### Held inputs (`hold_last=True`, #251)

Generalisation of the param-port retention: any input may opt into
"keep the last value across `clear()` and across the upstream's
`finish()`". Held inputs also do not count as lifecycle drivers in
the dispatcher's `_on_finish` decision — only non-held (clock)
inputs propagate finish.

Use case: an image source feeds a streaming sink that ticks N times
against a counter. The image is `hold_last=True`, so it stays alive
after its single emit; the counter is the clock that drives
firing and shutdown.

Visually: held ports render with a dashed `PORT_INPUT_COLOR` ring
in the editor.

### Filename templating (`core.filename_template`, #159)

`FileSink` and `VideoSink` use `core.filename_template.expand` to
resolve `$token$` placeholders in their `output_path` against the
incoming frame's `IoMeta` plus a per-sink **context** mapping.

Token resolution order:

1. Direct meta lookup (`$frame_index$`, custom keys).
2. Path-derived shortcuts when `meta["source_path"]` is set —
   `$source_stem$`, `$source_name$`, `$source_ext$`.
3. Run-context fallback (`$flow_name$` etc., context-injected by
   the sink).

Width syntax `$tok:N$` zero-pads numeric values.

`FileSink` additionally exposes every connected SCALAR input as a
`$<port_name>$` token — so a `tick` port driven by
`RangeSource(1..10)` resolves `$tick$` to the actual scalar value
`1, 2, …, 10`, distinct from the always-0-based `$frame_index$`
emit counter.

Multi-input merge: meta fields from every connected input are
unioned with later-declared inputs winning on key collisions; this
lets a held image's `source_path` and a clock's `frame_index` both
reach the template.

### Skip (`NodeBase.skipped`)

Blender-style mute: when a skippable node is toggled, `process()`
calls `_process_skipped()` instead of `process_impl()`. The default
implementation forwards each output from the first type-compatible
input (data-flow short-circuit). `_on_skipped_changed(skipped)` is
a hook subclasses override to react to the toggle (PlayGate uses
it to drain its buffered frames).

### Frame-index auto-stamping

`OutputPort.send(data)` stamps `data.meta["frame_index"]` from a
per-port emit counter and increments. Producers no longer thread
frame indices manually; sinks doing filename templating read
`meta["frame_index"]` directly.

## Lifecycle hooks (`NodeBase`)

| Hook                       | When                              | Override?         |
| -------------------------- | --------------------------------- | ----------------- |
| `before_run()`             | Once before each run              | No (`@final`)     |
| `_before_run_impl()`       | Inside `before_run`               | Yes               |
| `process_impl()`           | Per dispatch when data is ready   | Yes (abstract)    |
| `_process_skipped()`       | Per dispatch when `skipped=True`  | Yes (rare)        |
| `_on_finish()`             | All clock inputs finished         | Yes               |
| `_on_skipped_changed(b)`   | `skipped` flag flips              | Yes (rare)        |
| `after_run(success)`       | Once after each run               | No (`@final`)     |
| `_after_run_impl(success)` | Inside `after_run`                | Yes               |

Source-specific:

| Hook              | When                                               |
| ----------------- | -------------------------------------------------- |
| `iter_frames()`   | The streaming loop. Yields once per emitted frame. |
| `is_reactive`     | Property: True for one-shot, False for streaming.  |

## Known strain points

The push-only model handles image / video / data pipelines well.
Several VPL-style features strain it:

- **Backpressure / user-driven stepping.** `PlayGate` works around
  this with a node-local FIFO + Qt button click handler. Honest
  but the only debug node so far that needs UI-side coupling.
- **Control flow.** No native `if/else` routing or loop
  primitives. Conditional behaviour is faked with optional ports +
  per-node logic.
- **Sub-graphs / functions.** A graph cannot yet be encapsulated
  as a reusable node, which limits flow size and reuse.
- **External events.** Source nodes can model "data from a sensor,
  webhook, …" but routing user button clicks through the graph
  requires bolt-on callbacks (set_*_callback on nodes).
- **Multi-rate streams.** Round-robin gives equal weight to every
  source; an audio (48 kHz) and video (30 Hz) flow in the same
  graph would either drain the audio fast or stall the video.

## Planned framework extensions

These are tracked in GitHub issues and the refactoring backlog
(`refactoring.md`). The principle: **promote a bolt-on to a
framework primitive once it's needed by more than one node.**

- **Animation primitives (#246)** — `SlidingWindow` node + band
  hooks on `PlotXY` / `PlotSeries`. First real consumer of
  `hold_last`.
- **Stop / abort hook (planned).** A node-side hook so worker-blocking
  nodes (e.g. a true single-step `PlayGate`, an external-event
  source) can react to the user pressing Stop without the runner
  losing the ability to wind down. Currently `Flow._stop_requested`
  is only checked at the top of the round-robin loop, which is
  pre-empted by long-running `process_impl`s.
- **Event ports vs. data ports (planned).** A port type that
  carries pure trigger semantics — fires the dispatcher without
  payload. Cleans up the current `set_*_callback` pattern by
  modelling button clicks, external signals, and user input as
  first-class graph edges. Likely candidate once the second or
  third UI-coupled node lands.
- **Subgraphs / composite nodes (planned).** Encapsulate a graph
  as a single reusable node, with explicit input/output port
  surfaces. Unlocks loops (subgraph called N times), functions,
  and graph reuse.

## Anti-patterns to avoid

- **Reaching for `getattr(node, port.name, ...)` from outside the
  node.** That's the convention-coupling that #h6 in the
  refactoring backlog tracks. Use the port API
  (`port.data`, `port.default_value`).
- **Mutating an `IoData` after `send`.** The same instance is
  fanned out to every connected input; mutation creates spooky
  action across consumers. Use `clone(payload=...)` /
  `clone(meta_key=...)` to make a new envelope.
- **Bypassing `process_impl` / `iter_frames` for ad-hoc execution.**
  The runner's logging, stop check, and observer hook all sit in
  `process()`. Tests can call `process_impl` directly; production
  code paths must not.
- **Adding a per-node Qt dependency.** Nodes are Qt-free; UI
  marshalling lives in `src/ui/preview_widgets.py`. The
  worker-thread → UI-thread hop crosses via queued signal, not by
  the node calling Qt.
- **Silent metadata loss.** When a filter constructs an output via
  `IoData.from_*(...)`, the source's `meta` is dropped. Prefer
  `in_data.clone(payload=new_array)` so provenance survives the
  filter chain.

## Maintenance

When the framework's public surface changes (a new lifecycle hook,
a new port flag, a new IoData factory), update this document in
the same PR. New strain points discovered while building a feature
go to `refactoring.md`; resolved items move to its Resolved
section with the date and PR.

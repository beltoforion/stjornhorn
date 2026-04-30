# Internal documentation

Maintainer-facing notes — architecture, design sketches, refactoring
backlog. End-user docs (the in-app welcome page, the node catalog)
live one level up under `doc/`.

## Contents

| Document                                      | Purpose                                                        |
| --------------------------------------------- | -------------------------------------------------------------- |
| [`dataflow.md`](./dataflow.md)                | How data moves through a flow at runtime; the framework reference. |
| [`refactoring.md`](./refactoring.md)          | Living backlog of architectural / SOLID / code-quality issues. |
| [`diagrams/`](./diagrams/)                    | SVG sketches referenced from the docs above.                   |

## Maintenance

- `dataflow.md`: update in the same PR whenever the framework's
  public surface changes (a new lifecycle hook, a new port flag, a
  new IoData factory). New strain points discovered while building
  go to `refactoring.md`.
- `refactoring.md`: append findings under the right severity
  bucket; on landing, move the entry to **Resolved** with the date
  and PR — don't delete it. Update the "Last reviewed" line during
  sweeps.
- `diagrams/`: SVGs editable directly. Reference them from prose
  with relative links.

These docs are **freely editable** — Claude Code may push changes
without asking, same rule as `CLAUDE.md` / `doc/welcome.html` /
`README.md`.

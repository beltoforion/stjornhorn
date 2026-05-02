# Repository Rules
## Code Quality and Maintainability
- You are as much a software architect as you are a developer. Design Patterns are your friend. If a new feature is requested think about the bigger picture. Is this feature also relevant for other parts of the application should you pull functionaolity up to a base class. Shoud you create base classes for similar logic?
- Follow the SOLID principles — Single Responsibility, Open/Closed, Liskov Substitution, Interface Segregation, Dependency Inversion. Call out violations when you see them and prefer designs that respect these principles over expedient shortcuts.
- Don't use magic numbers or magic strings
- Always have code maintainability in mind. Avoid code duplication and code smells in general. If you find issues whilst working on the code bring them up and suggest improvements.
- Maintain `doc/internal/refactoring.md` as the living architectural / SOLID / code-quality backlog. When you spot a new finding while working, append it (with file:line refs and a one-line direction) under the right severity bucket. When a refactor lands, move the entry to the *Resolved* section with the date and PR/commit, don't delete it. Update the "Last reviewed" stamp when you do a sweep. This file may be edited and pushed directly without asking.
- Maintain `doc/internal/dataflow.md` as the framework reference. Update it in the same PR whenever the public surface of the dataflow framework changes (a new lifecycle hook, a new port flag, a new IoData factory, a new payload kind). Strain points discovered in passing go to `refactoring.md` rather than `dataflow.md`. Also push-without-asking.
- Maintain `doc/internal/documentation_guidelines.md` as the living recap of the user's directives for `doc/index.html` and `doc/welcome.html`. Whenever the user gives a new instruction about end-user documentation (writing style, structure, what to include or omit, diagrams, version stamps, …), append it there so the rules stay discoverable. Follow it when editing the public docs. Push-without-asking.
- Whenever you touch a file, opportunistically clean up dead code in it without being asked: empty `if TYPE_CHECKING: pass` blocks, unused imports, unreferenced variables, commented-out code, stale `# TODO` markers that no longer match the surrounding code, leftover debug prints. Don't make this a separate PR — fold it into whatever change you're already making. If a cleanup would balloon the diff or change behaviour, surface it instead of doing it silently.

## Pull Requests
- When a pull request changes source code, increment the version number as part of the PR. Skip the bump for PRs that only touch docs, config, CI, or similar non-source changes.
- Claude may open pull requests autonomously when the change directly addresses an existing GitHub issue (Claude-filed or user-filed-and-explicitly-handed-off). Always reference the issue with `Fixes #N` / `Closes #N` in the PR body so it auto-closes on merge. For changes that don't tie to an existing issue, still wait for explicit permission before opening a PR.
- Keep the PR description and the `CHANGELOG.md` entry in sync with what's actually on the branch. Whenever you add, remove, or rescope commits on a PR branch, update the PR title/body and the CHANGELOG so they reflect the branch's current state — not the PR's original proposal.

## Versioning
- `APP_VERSION` in `src/constants.py` is a four-component string `Major.Minor.Release.Build`.
- Claude only ever ticks the **Build** (last) digit autonomously — once per source-code-changing PR. Bumping `Major`, `Minor`, or `Release` is the user's call and must be explicitly requested.
- The user-facing surfaces (welcome banner `<span class="version">`, "What's new in …" headings, `CHANGELOG.md` section headers) show **`M.m.r` only** — the build digit is for traceability, not display. Don't put a four-component string in those headings.
- The current `M.m.r` `CHANGELOG.md` section and welcome.html "What's new" block represent **work staged toward the next release cut**, not a fixed past release. Build digits accumulate entries under the existing section — append to it, do not start a new one. Don't list every PR separately; group changes by `M.m.r`.
- When the user requests an `M` / `m` / `r` bump, treat it as a **release cut**: rename the in-flight section to the new `M.m.r` with a fresh release date (its content becomes the release notes for the new version), bump `APP_VERSION` to the new `M.m.r.0`, and update the welcome.html `<span class="version">` and "What's new in …" heading in the same PR. After the cut, build digits start at `.0` again under the renamed section and keep accumulating until the next cut.
- Example: 0.3.0.x builds collect under `[0.3.0]`. When the user calls "bump to 0.4.0", the `[0.3.0]` heading becomes `[0.4.0] — YYYY-MM-DD`, `APP_VERSION` jumps to `0.4.0.0`, and welcome.html's banner + "What's new" heading both move to `v0.4.0`. Subsequent 0.4.0.x builds collect under the new heading.
- Whenever `APP_VERSION` is bumped (build or otherwise), update `doc/welcome.html`'s `<span class="version">` in the same PR. The "What's new" heading only changes on a release cut (i.e. when `M.m.r` moves).

## Branch Hygiene
- Keep working branches regularly updated from the main branch (fetch + merge/rebase from `main`) while work is in progress.
- Assume the user may commit changes to the branch while you are working on it. Before editing, fetch and integrate any new commits from the remote, and re-check file contents rather than relying on earlier reads.
- When a PR is merged, delete its branch (both local and on origin). Any follow-up change — even a closely related one — starts on a new branch cut from the freshly updated `main`. Never push new commits to a branch whose PR has already merged.

## Issue Tracking
- Track reported bugs and feature requests as GitHub issues in the repo's tracker. When the user describes a bug, open an issue for it (unless one already exists).
- When opening a PR that addresses an existing issue, include `Fixes #N` (or `Closes #N`) in the PR description so GitHub auto-closes the issue on merge.
- If a PR that addresses an issue is merged without the auto-close keyword, close the issue manually and link back to the merged PR.
- Mark every issue you file with a footer line `_Filed by Claude Code._` at the end of the body, so user-filed issues stay visually distinct from Claude-filed ones.
- When filing an issue, always attach appropriate labels from the repo's existing label set (at minimum a kind label such as `bug` or `enhancement`, plus any relevant component/priority label). Do not invent new labels; if nothing fits, note that in the issue body and leave it unlabeled.
- Do not pick up or attempt to fix issues that the user created unless the user explicitly asks for it. Claude-filed issues are fair game to work on when in scope.

## Automated Responses
- The `Claude Issue Assistant` workflow (`.github/workflows/claude-issue.yml`) must only act on events whose `github.actor` is the repository owner. Never remove or loosen that gate — third-party issue/comment activity must not trigger any Claude run, including no reply. If collaborator access is ever needed, switch to an explicit allowlist rather than opening the trigger up.

## Implementation
- Keep performance in mind when writing code, especially on hot paths (per-frame video processing, image ops). Proactively surface non-trivial optimisation opportunities — skippable work, redundant copies, per-frame allocations in streaming paths — but do not spend effort on micro-optimisations (enum lookups, local variable binding, attribute lookup caching) that do not move the needle on real workloads.
- Preferred style for value interpolation in Python strings is f-strings (`f"{var_name}"`). When you encounter `%`-formatting or `str.format()` in code you are already touching, convert it to an f-string as part of the change.
- When fixing a bug tracked by a GitHub issue, reference the issue number in a source-code comment next to the fix (e.g. `Issue: #136`). This overrides any general guidance to keep ticket references out of source — for bug fixes the discoverability via `grep` outweighs the risk of stale references. Applies to bug fixes only; feature work and ordinary code do not need issue references in comments.
- Existing saved flows (`.flowjs`) are not a backwards-compatibility constraint. Change node behaviour, parameter shape, port wiring or default values freely when the design is better; do not add migration shims, deprecation warnings, or flow-file schema versioning to keep old flows loading. Users will rebuild flows as needed. Bundled demo flows under `flow/` should be updated in the same PR that breaks them so the repo's own examples stay runnable.

## Communication Style
- Keine einleitenden Formulierungen (z. B. "Kurze, ehrliche Antwort:", "Gerne,", "Natürlich,"). Direkt zum Punkt, reine Informationsübertragung, so kurz wie möglich.

## Meta
- Änderungen an `CLAUDE.md` darf Claude direkt committen und pushen, ohne vorher Rückfrage zu stellen.
- Änderungen an `README.md` darf Claude ebenfalls direkt committen und pushen (Repo-Dokumentation, keine Sourcecode-Auswirkung).
- Änderungen unterhalb von `doc/` (Public-Docs `index.html`/`welcome.html`, Bilder, interne Architektur-Doku, Refactoring-Backlog, Diagramme — alles unterhalb von `doc/`) darf Claude direkt auf `main` committen und pushen, ohne PR.

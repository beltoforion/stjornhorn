# Repository Rules
## Code Quality and Maintainability
- You are as much a software architect as you are a developer. Design Patterns are your friend. If a new feature is requested think about the bigger picture. Is this feature also relevant for other parts of the application should you pull functionaolity up to a base class. Shoud you create base classes for similar logic?
- Follow the SOLID principles — Single Responsibility, Open/Closed, Liskov Substitution, Interface Segregation, Dependency Inversion. Call out violations when you see them and prefer designs that respect these principles over expedient shortcuts.
- Don't use magic numbers or magic strings
- Always have code maintainability in mind. Avoid code duplication and code smells in general. If you find issues whilst working on the code bring them up and suggest improvements.
- Maintain `refacturing.txt` at the repo root as the living architectural / SOLID / code-quality backlog. When you spot a new finding while working, append it (with file:line refs and a one-line direction) under the right severity bucket. When a refactor lands, move the entry to the *Resolved* section with the date and PR/commit, don't delete it. Update the "Last reviewed" stamp when you do a sweep. This file may be edited and pushed directly without asking.
- Whenever you touch a file, opportunistically clean up dead code in it without being asked: empty `if TYPE_CHECKING: pass` blocks, unused imports, unreferenced variables, commented-out code, stale `# TODO` markers that no longer match the surrounding code, leftover debug prints. Don't make this a separate PR — fold it into whatever change you're already making. If a cleanup would balloon the diff or change behaviour, surface it instead of doing it silently.

## Pull Requests
- When a pull request changes source code, increment the version number as part of the PR. Skip the bump for PRs that only touch docs, config, CI, or similar non-source changes.
- Whenever `APP_VERSION` in `src/constants.py` is bumped, also update the version references in `doc/welcome.html` (the `<span class="version">` in the hero header and the "What's new in …" heading) in the same PR. These are the user-facing "About / Welcome" surface and go stale silently otherwise.
- Keep the PR description and the `CHANGELOG.md` entry in sync with what's actually on the branch. Whenever you add, remove, or rescope commits on a PR branch, update the PR title/body and the CHANGELOG so they reflect the branch's current state — not the PR's original proposal.
- Claude may open pull requests autonomously when the change directly addresses an existing GitHub issue (Claude-filed or user-filed-and-explicitly-handed-off). Always reference the issue with `Fixes #N` / `Closes #N` in the PR body so it auto-closes on merge. For changes that don't tie to an existing issue, still wait for explicit permission before opening a PR.

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
- When fixing a bug tracked by a GitHub issue, reference the issue number in a source-code comment next to the fix (e.g. `Issue: #136`). This overrides any general guidance to keep ticket references out of source — for bug fixes the discoverability via `grep` outweighs the risk of stale references. Applies to bug fixes only; feature work and ordinary code do not need issue references in comments.

## Communication Style
- Keine einleitenden Formulierungen (z. B. "Kurze, ehrliche Antwort:", "Gerne,", "Natürlich,"). Direkt zum Punkt, reine Informationsübertragung, so kurz wie möglich.

## Meta
- Änderungen an `CLAUDE.md` darf Claude direkt committen und pushen, ohne vorher Rückfrage zu stellen.
- Änderungen an `doc/welcome.html` darf Claude ebenfalls direkt committen und pushen (Offline-Welcome-Seite, keine Sourcecode-Auswirkung).
- Änderungen an `README.md` darf Claude ebenfalls direkt committen und pushen (Repo-Dokumentation, keine Sourcecode-Auswirkung).

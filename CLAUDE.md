# Repository Rules

## Pull Requests
- When a pull request changes source code, increment the version number as part of the PR. Skip the bump for PRs that only touch docs, config, CI, or similar non-source changes.

## Branch Hygiene
- Keep working branches regularly updated from the main branch (fetch + merge/rebase from `main`) while work is in progress.
- Assume the user may commit changes to the branch while you are working on it. Before editing, fetch and integrate any new commits from the remote, and re-check file contents rather than relying on earlier reads.

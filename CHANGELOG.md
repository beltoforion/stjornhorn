# Changelog

All notable changes to Stjörnhorn (repo: `image-inquest`) are tracked
in this file.

The format loosely follows [Keep a
Changelog](https://keepachangelog.com/en/1.1.0/) and the project aims
to adhere to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
once a first tagged release is cut.

## [Unreleased]

## [0.3.0] — 2026-04-29

### Changed

- `APP_NAME` aligned with the brand: now `"Stjörnhorn"` (was the legacy
  `"Image-Inquest"`). Affects the Qt application name and the startup
  log line; user-visible captions are unchanged because they already
  use `APP_DISPLAY_NAME`, which read `"Stjörnhorn"` before.

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

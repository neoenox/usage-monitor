# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Dates are in JST.

## [Unreleased]

### Changed

- End-to-end tests that launch a real process now report why it failed. They all go through
  a shared `run_process` helper (`tests/conftest.py`) that names the command, the timeout,
  the measured duration, the exit code and the tail of both streams, so a hang can be told
  apart from a slow cold start from a real crash; a single unreproduced failure during the
  v0.6.4 release could not be identified for want of exactly this. `--durations=10` is now
  always on, and `USAGE_MONITOR_TEST_TIMEOUT` raises the default 120 s timeout for a slow
  runner (#90).

## [v0.6.4] - 2026-10-18

### Added

- Tagging is now the release trigger. `.github/workflows/release.yml` checks the tag
  against `master`, `monitor.__version__` and the CHANGELOG, runs the suite with the
  coverage floor, builds both executables, verifies their version resource and SHA-256,
  and publishes the release with notes taken from the changelog section itself
  (`release_notes.py`). A draft or partial upload left by an interrupted run is repaired
  with `--clobber` and un-drafted instead of needing manual uploads (#84, #85).

### Changed

- Covered the browser recovery safety paths: `browser_recover.py` went from 67% to 98%
  coverage, closing the only module below the 70% floor. The new tests pin the behaviour
  the module exists for — bounded one-step repair, no loops, no raises, no payloads in the
  log (#83).

### Fixed

- `release_notes.py` no longer raises when the changelog text contains a character the
  console code page cannot encode (an em dash on a cp932 console); unencodable characters
  are escaped on stdout, and the `--out` path used by the release workflow was never
  affected (#87).

### Docs

- The build instructions match `build.ps1` again: the native host build no longer shows a
  PyInstaller command that omits the version resource (#81).
- Recorded a Codex eligibility review: the release gate is confirmed for the intended
  local/self-hosted/open-source scope, while commercial or hosted distribution still
  needs the Sign in with ChatGPT path plus a provider agreement (#82).
- Documented the release procedure and its contract in `docs/RELEASE.md`, including that
  released assets are built on the runner and are not expected to be byte-identical to a
  local build (#84, #86).

## [v0.6.3] - 2026-10-18

### Fixed

- The packaged executables now expose their version. `build.ps1` embeds a
  Windows version resource generated from `monitor.__version__`, so the file
  properties (Details) and `(Get-Item .\usage-monitor.exe).VersionInfo` report
  the release version. `usage-monitor.exe --version` no longer starts the GUI;
  it exits immediately without a window and prints only when a console is
  attached (#77, #78).

### CI

- GitHub Actions run on Node 24 with the current action majors
  (`actions/checkout@v7`, `actions/setup-python@v7`,
  `actions/upload-artifact@v7`), which removes the Node.js 20 deprecation
  annotation from every run (#76).

## [v0.6.2] - 2026-10-18

### Fixed

- Report the current release version again. `__version__` had stayed at `0.5.2`
  while `v0.6.0` and `v0.6.1` were tagged, so the `v0.6.1` build showed `0.5.2`
  in the window title and for `python monitor.py --version`.

### CI

- Fail the suite when `monitor.__version__` drifts from the newest CHANGELOG
  release, so a release can no longer ship a stale version string.

## [v0.6.1] - 2026-10-17

### Fixed

- Surface a pending extension reload in the settings status hints, not only in
  the diagnosis text, so the remaining setup step is not missed (#71).

### CI

- Upload the HTML coverage report as a build artifact, kept even when tests fail
  (#70).

## [v0.6.0] - 2026-10-16

Everything since `v0.5.0` (2026-09-30). This release removes Claude credential
extraction in favour of documented, credential-free observation paths.

### Added

- Claude browser linkage: read usage from the user's own Claude usage settings
  page through a Chrome extension plus a local native-messaging host. Only
  numeric utilization/reset values are forwarded; no cookies or credentials
  (#45, #46).
- Credential-free Claude statusline export with a consented, reversible setup:
  the existing statusline is backed up and restored, and only numeric fields and
  observation timestamps are stored (#37, #44).
- First-run provider setup and observation states in the settings tab, including
  four distinct Claude setup states (`no_claude_code`, `statusline_missing`,
  `awaiting_observation`, `receiving`) (#37, #60).
- Extension settings diagnosis now shows when the unpacked extension was last
  loaded and flags a pending reload when its files are newer (#64, #65).
- Reset-aware usage forecast segmentation; observed-sample forecasts shared
  between the CLI and GUI (#25, #33, #51).
- Configurable alert thresholds in the GUI and a daily morning-report balloon
  (#27).
- Branded application icons (#49).
- Bilingual (Japanese/English) usage-page parser and one-click browser-linkage
  diagnosis and recovery (#45, #46).

### Changed

- Claude usage is now read through the official statusline interface; the custom
  OAuth polling path has been retired and is a no-op (#44).
- The weekly/forecast view was simplified to a flat budget display (#33).
- Executable builds are standardized on `build.ps1` (#31).

### Fixed

- Keep the last successful quota values when offline, with timestamps (#36).
- Read current Codex quotas through the official app-server and compare
  rate-limit event timestamps as instants rather than strings (#21, #34).
- Never invoke a model to recover usage authentication (#37).
- Distinguish exported observations from the legacy cached fallback and mark
  stale values honestly (#37).
- Normalize saved alert thresholds to numeric values and reject malformed cached
  reset epochs (#27, #29).
- History store: enable WAL with a busy timeout for parallel GUI/CLI writes, and
  compute local-day boundaries across DST transitions (#14, #26).
- GUI: schedule a single disconnected refresh tick, and create Windows shortcuts
  with Unicode-safe `IShellLinkW` instead of ANSI scripts (#17, #28).

### Security

- Retired Claude credential access: the monitor no longer reads, stores, or
  intermediates credentials, and cannot use model calls to recover them
  (#37).
- Documented provider authentication and distribution constraints, including
  the browser status-page path review (restricted; personal use only) in
  `docs/DISTRIBUTION.md` (#37, #62).

### Docs

- Added/updated `docs/DISTRIBUTION.md`, `docs/BROWSER_CLAUDE.md`,
  `docs/ROLLBACK.md`, and `docs/ISSUE_VERIFICATION.md` (#37, #50, #52, #58,
  #62, #63).

### CI

- Test on Linux under a virtual display in addition to Windows (#23).
- Run checks on stacked PRs and verify the packaged numeric export and browser
  host.
- Measure test coverage on the Windows job with a 70% floor (#66).

## [v0.5.0] - 2026-09-30

Baseline tagged release. See the repository history for earlier changes.

[Unreleased]: https://github.com/neoenox/usage-monitor/compare/v0.6.4...HEAD
[v0.6.4]: https://github.com/neoenox/usage-monitor/compare/v0.6.3...v0.6.4
[v0.6.3]: https://github.com/neoenox/usage-monitor/compare/v0.6.2...v0.6.3
[v0.6.2]: https://github.com/neoenox/usage-monitor/compare/v0.6.1...v0.6.2
[v0.6.1]: https://github.com/neoenox/usage-monitor/compare/v0.6.0...v0.6.1
[v0.6.0]: https://github.com/neoenox/usage-monitor/compare/v0.5.0...v0.6.0
[v0.5.0]: https://github.com/neoenox/usage-monitor/releases/tag/v0.5.0

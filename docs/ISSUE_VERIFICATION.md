# Remaining issue implementation and verification

Status (current, 2026-10-18): all review-branch work has landed on `master` and no issue remains open. Verified at `013c05d`: `python -m pytest tests -q` -> 208 passed, 6 skipped; Windows (with a 70% coverage floor, 76.93% measured) and Linux CI pass on every PR, now on Node 24 actions with no deprecation annotation. Releases `v0.6.0` through `v0.6.3` are published; the `v0.6.3` downloads were verified after publication (see the 2026-10-18 v0.6.3 record below). The historical review snapshot below (PR #39 / `6dfdda2` / 137 tests) is retained for the record.

## PR dependency and scope (historical — resolved)

These stacked PRs were the review scaffolding for the issue work below and have all since landed on `master`:

- PR #34: compare Codex rate-limit event timestamps as instants (#21) — merged 2026-10-07.
- PR #35: resilience/UI/history changes — merged 2026-10-08.
- PR #36: live Codex usage and persistent offline quota fallback — merged 2026-10-08.
- PR #39: stacked on `fix/codex-live-quotas`, integrated #35 and the remaining issue work — merged 2026-10-08.

The original caveats (do not merge #39 independently; reconcile #35/#36 first) no longer apply because all of them are merged. Follow-on work continued directly on `master` (#44–#51).

## Issue acceptance map

| Issue | Resolution | Evidence |
| --- | --- | --- |
| #20 | One-pass Codex JSONL scan; no redundant file read | `tests/test_codex_single_pass.py` |
| #22 | Original OS-store fallback integrated from #35, then superseded by approved removal of all Claude credential reading. Closed as superseded 2026-10-16 (see closure record) | `tests/test_retired_oauth.py`, `tests/test_monitor.py` |
| #23 | Non-Windows CLI no longer depends on Win32 tray import | Linux CI in `.github/workflows/ci.yml`, CLI regressions |
| #24 | OAuth tests no longer use machine auth; retired interfaces and custom HOME are isolated. Closed as superseded 2026-10-16 (see closure record) | `tests/test_retired_oauth.py`, `tests/test_monitor.py` |
| #25 | CLI/GUI share observed-sample forecast; malformed history cannot crash rendering | `tests/test_forecast_shared.py`, `tests/test_forecast_invalid.py` |
| #26 | SQLite timeout/WAL from #35 | `tests/test_history_concurrency.py` |
| #27 | Thresholds normalize to numbers before serialization | `tests/test_settings_roundtrip.py` |
| #28 | Windows argument quoting from #35; replaced ANSI WScript shortcut interface with native IShellLinkW/IPersistFile after English-runner failure; real COM test with spaces/Japanese/apostrophe paths | `tests/test_windows_shortcut.py` |
| #29 | RemainingLabel resilience from #35 | `tests/test_gui_logic.py` |
| #30 | Load alert settings once per alert pass from #35 | GUI/tray regression tests |
| #31 | Spec already ignored/untracked; README build uses `build.ps1` | `git ls-files '*.spec'` empty; `git check-ignore usage-monitor.spec` succeeds; exe build succeeds |
| #37 | Approved numeric-only statusline adapter, explicit consent/replacement, backup/restore and official-tool setup guidance; no credential extraction/network refresh/model recovery. Closed 2026-10-16 after the remaining scope landed: per-state setup matrix (#60), browser-path ToS review (#62), restart/offline E2E (#59) | `tests/test_claude_export.py`, `tests/test_claude_setup.py`, `tests/test_no_model_refresh.py`, `tests/test_packaged_export.py`, `DISTRIBUTION.md` |

## Security and recovery evidence

- Actual packaged export test supplies an extra secret field and verifies it is not persisted.
- Export whitelists finite numeric usage/reset fields, preserves observation time, and uses unique staging files for concurrent sessions.
- Interrupted setup supports retry/restore. Existing statusline replacement requires a separate explicit consent; its display is suspended, not chained through arbitrary shell commands. Restoration preserves unrelated settings and refuses changed statusline commands.
- Cache values remain timestamped reference values, never a reason for fabricated quota resets, forecasts, notifications or new history records.
- Claude updates only when official Claude Code emits rate-limit statusline data; eligible plan/session and window availability are required. No independent live polling.
- Codex tokens stay under official Codex management. No standalone login, bundled CLI, API-key billing or cross-account aggregation is implemented.

## Remaining release constraints

See `DISTRIBUTION.md` for primary sources. Numeric export is not provider endorsement of this standalone monitor. Commercial/hosted Codex distribution eligibility requires confirmation. Do not advertise general commercial release readiness.

Setup acceptance review, final rebuilt suite and combined CI completed. This section records the review state at the time, not merge approval or unrestricted commercial release; later merges and issue closures were separately authorized.

## 2026-10-16 closure record

Reviewed against master after #44 (`85eb182`) retired all Claude credential reading. Both issues are obsolete as written and are closed as superseded; the retired behavior is pinned by an existing contract test, so no new regression test was required.

- #22 "credentials.json無効時にOSストアへフォールバックしない": superseded by #44 — the OS-store fallback path no longer exists. Contract fixed by `tests/test_retired_oauth.py`, which forces `claude_token_from_os_store` to raise if invoked and asserts an `unsupported` result. Closed as superseded.
- #24 "test_fetch_oauth_ok が実OSストア依存でflaky": the flaky test no longer exists on master (OAuth acceptance path retired by #44); its intent is covered by the isolated-home contract test above. Closed as superseded.
- Branch cleanup: the issues' branches (`fix/credentials-no-os-store-fallback`, `fix/test-oauth-isolation-24`) are unlandable (target code retired) and were deleted; only `master` remains on the remote.

## 2026-10-17 release artifact verification (v0.6.1)

Re-verified the published `v0.6.1` release downloads (not the local build) to confirm the shipped binaries match the tagged source and still work:

- SHA-256 of the downloaded `usage-monitor.exe` and `usage-monitor-browser-host.exe` is byte-identical to `dist/` built from `master` (`e686ce4`).
- Packaged numeric export (`usage-monitor.exe --claude-export`, `LOCALAPPDATA` redirected to a temp dir) exits 0, writes `claude-quota.json` with `five_hour.utilization == 25`, and does not persist the extra `secret` field.
- Browser host: `--import` exits 0 and writes `five_hour`/`seven_day` utilization; `--register not-a-valid-id` exits non-zero without writing a manifest; a no-argument launch exits non-zero mentioning the extension origin.
- `usage-monitor.exe` embeds the brand icon (`app.ico`).

Remaining manual step (owner only, cannot be automated): reload the unpacked extension at `chrome://extensions` so the branding files on disk take effect. The settings tab now flags this as `拡張の更新が未反映（chrome://extensionsで再読み込み）` (#65, #71).

## 2026-10-18 version drift fix and v0.6.2 release

`__version__` stayed at `0.5.2` while `v0.6.0` and `v0.6.1` were tagged (`git show v0.6.1:monitor.py` -> `0.5.2`), so the v0.6.1 build displayed `0.5.2` in the window title (`gui.py:315`) and for `python monitor.py --version` (`monitor.py:580`). The old `test_version` only checked the `X.Y.Z` shape, so nothing caught it. Fixed in PR #74 (`49a2449`, `__version__ = "0.6.2"`) together with a guard that fails CI when `__version__` drifts from the newest CHANGELOG release, when release headings are not newest-first, or when the top heading / `[Unreleased]` lose their link definitions (`tests/test_version_consistency.py`).

Re-verified the published `v0.6.2` downloads (not the local build), as with v0.6.1:

- Both downloaded assets are byte-identical to `dist/` built from `49a2449`: SHA-256 `usage-monitor.exe` = `E097A76594125D8556D90264C6728EE1D957B2DA4CE1010A724B668CEDC00444`, `usage-monitor-browser-host.exe` = `176603062F4B7173972167677EE88E8465AA1C5FC42E9E264823F4F214320CE8`.
- The `monitor` module extracted from the frozen `usage-monitor.exe` contains exactly one version-like constant: `0.6.2`.
- Packaged numeric export (`usage-monitor.exe --claude-export`, `LOCALAPPDATA` redirected to a temp dir) exits 0, writes `claude-quota.json` with `five_hour.utilization == 25`, and does not persist the extra `secret` field.
- Browser host: `--import` exits 0 and writes `five_hour`/`seven_day` utilization; `--register not-a-valid-id` exits 1 without writing a manifest; a no-argument launch exits 1 mentioning the extension origin.
- `usage-monitor.exe` still embeds the brand icon data (`app.ico` marker present).
- `TEST_PACKAGED_EXPORT=1 python -m pytest tests/test_packaged_export.py tests/test_packaged_browser_host.py -q` -> 5 passed.

Limitation found while verifying (not fixed here): `usage-monitor.exe --version` does not print a version. The frozen entry point is `gui.py`, which only special-cases `--claude-export`, so the flag launches the GUI instead, and a windowed build has no console to print to. The packaged version is confirmed by the window title; the CLI form is `python monitor.py --version`. Fixed in v0.6.3 (see below).

The manual extension reload above still applies to this release: the unpacked extension must be reloaded at `chrome://extensions` for updated on-disk assets (icons, `manifest.json`) to take effect.

## 2026-10-18 v0.6.3 release (packaged version exposure)

Follow-on to the drift fix above: the packaged executables now expose their version instead of only showing it in the window title. `build.ps1` generates a Windows version resource from `monitor.__version__` with the new `windows_version.py` and passes `--version-file` for both executables; `gui.py` handles `--version` by exiting 0 without creating a window, printing only when a console is attached (Issue #77, PR #78). The CI job also moved to the current action majors (`actions/checkout@v7`, `actions/setup-python@v7`, `actions/upload-artifact@v7`, all Node 24) in PR #76, which removed the Node.js 20 deprecation annotation from every run.

Re-verified the published `v0.6.3` downloads (not the local build):

- Both downloaded assets are byte-identical to `dist/` built from `013c05d`: SHA-256 `usage-monitor.exe` = `CC36F4A99BBAEFECC0B86B09CB8D71BF78570B4D655648C653B887CE3BCA65AE`, `usage-monitor-browser-host.exe` = `64B26046BC2D2A5B20BAEB2E86A59E8271E8148ED83B2C121138C3A0037A9ABA`.
- Embedded version resource: fixed info `0.6.3.0` for both executables; `(Get-Item .\usage-monitor.exe).VersionInfo` reports FileVersion / ProductVersion `0.6.3` with OriginalFilename `usage-monitor.exe`.
- The `--version` limitation above is fixed: `usage-monitor.exe --version` exits 0 in about 1.7 s and creates no window (previously it started the GUI and never exited). As a windowed build it prints nothing, so the version is confirmed by the window title, the file properties, or `python monitor.py --version`.
- Packaged numeric export (`usage-monitor.exe --claude-export`, `LOCALAPPDATA` redirected to a temp dir) exits 0, writes `claude-quota.json` with `five_hour.utilization == 25`, and does not persist the extra `secret` field.
- Browser host: `--import` exits 0 and writes `five_hour`/`seven_day` utilization; `--register not-a-valid-id` exits 1 without writing a manifest; a no-argument launch exits 1 mentioning the extension origin.
- `usage-monitor.exe` still embeds the brand icon data (`app.ico` marker present).
- `TEST_PACKAGED_EXPORT=1 python -m pytest tests/test_packaged_export.py tests/test_packaged_browser_host.py -q` -> 6 passed (the version-resource assertion is new; `tests/test_windows_version.py` covers the generator and the `--version` entry point in the normal suite).

The `docs/DISTRIBUTION.md` release gate is unchanged: Codex eligibility for commercial/hosted distribution is still open. The manual extension reload also still applies to this release.

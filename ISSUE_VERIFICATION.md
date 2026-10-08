# Remaining issue implementation and verification

Status: implementation review in draft PR #39; no merges or issue closures. Local Windows verification at commit 7c7a0e1: 135 tests passed, including actual built executable numeric export, with zero skips. Later setup/documentation changes require a final rerun.

## PR dependency and scope

- PR #36: live Codex usage and persistent offline quota fallback.
- PR #35: resilience/UI/history changes. Its implementation is merged into the review branch locally, not merged on GitHub.
- PR #39: stacked on `fix/codex-live-quotas`, includes integration of #35 and remaining issue work. Before merging, merge/reconcile #35 and #36 and retarget/review #39 against master. Do not merge this PR independently without checking this dependency.
- CI now includes the stacked base and Windows build/export integration. Prior #36 CI failure is not claimed fixed on that branch; verify combined branch and reconcile before merge.

## Issue acceptance map

| Issue | Resolution | Evidence |
| --- | --- | --- |
| #20 | One-pass Codex JSONL scan; no redundant file read | `tests/test_codex_single_pass.py` |
| #22 | Original OS-store fallback integrated from #35, then superseded by approved removal of all Claude credential reading | `tests/test_retired_oauth.py`, `tests/test_monitor.py` |
| #23 | Non-Windows CLI no longer depends on Win32 tray import | Linux CI in `.github/workflows/ci.yml`, CLI regressions |
| #24 | OAuth tests no longer use machine auth; retired interfaces and custom HOME are isolated | `tests/test_retired_oauth.py`, `tests/test_monitor.py` |
| #25 | CLI/GUI share observed-sample forecast; malformed history cannot crash rendering | `tests/test_forecast_shared.py`, `tests/test_forecast_invalid.py` |
| #26 | SQLite timeout/WAL from #35 | `tests/test_history_concurrency.py` |
| #27 | Thresholds normalize to numbers before serialization | `tests/test_settings_roundtrip.py` |
| #28 | Escaped PowerShell values and Windows argument quoting from #35; real COM test with spaces/Japanese/apostrophe paths | `tests/test_windows_shortcut.py` |
| #29 | RemainingLabel resilience from #35 | `tests/test_gui_logic.py` |
| #30 | Load alert settings once per alert pass from #35 | GUI/tray regression tests |
| #31 | Spec already ignored/untracked; README build uses `build.ps1` | `git ls-files '*.spec'` empty; `git check-ignore usage-monitor.spec` succeeds; exe build succeeds |
| #37 | Approved numeric-only statusline adapter, explicit consent/replacement, backup/restore and official-tool setup guidance; no credential extraction/network refresh/model recovery | `tests/test_claude_export.py`, `tests/test_claude_setup.py`, `tests/test_no_model_refresh.py`, `tests/test_packaged_export.py`, `DISTRIBUTION.md` |

## Security and recovery evidence

- Actual packaged export test supplies an extra secret field and verifies it is not persisted.
- Export whitelists finite numeric usage/reset fields, preserves observation time, and uses unique staging files for concurrent sessions.
- Interrupted setup supports retry/restore. Existing statusline replacement requires a separate explicit consent; its display is suspended, not chained through arbitrary shell commands. Restoration preserves unrelated settings and refuses changed statusline commands.
- Cache values remain timestamped reference values, never a reason for fabricated quota resets, forecasts, notifications or new history records.
- Claude updates only when official Claude Code emits rate-limit statusline data; eligible plan/session and window availability are required. No independent live polling.
- Codex tokens stay under official Codex management. No standalone login, bundled CLI, API-key billing or cross-account aggregation is implemented.

## Remaining release constraints

See `DISTRIBUTION.md` for primary sources. Numeric export is not provider endorsement of this standalone monitor. Commercial/hosted Codex distribution eligibility requires confirmation. Do not advertise general commercial release readiness.

Before final completion: finish setup acceptance review, verify fresh combined CI, rerun full tests against latest build, and update PR/issue comments with final evidence. No GitHub merge or automatic closure is authorized.

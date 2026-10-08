# Local Claude acquisition rollback (2026-10-09)

At the user's request, restore the Claude direct acquisition implementation from 96a6895, while retaining subsequent Codex, cache validation, forecast, SQLite and native Unicode shortcut fixes.

- Temporary probe configuration removed from the active Claude settings.
- Original pre-export statusline restored using its backup, preserving unrelated settings.
- scan_claude now uses fetch_claude_oauth; statusline setup buttons removed.
- Model-based authentication recovery remains disabled.
- The earlier export-only security/distribution statements in README, DISTRIBUTION and ISSUE_VERIFICATION describe the prior merged redesign, not this local rollback. This rollback restores credential use and does not resolve the previously documented provider-policy concerns; it is not authorization for general distribution.
- Initial direct acquisition returned `expired`. Boundary diagnostics established refresh HTTP 429 and existing-access-token usage HTTP 401, rather than guessing from the application's collapsed status.
- Official `claude auth login --claudeai` in a visible terminal produced fresh credentials without invoking a model. Never request authorization codes in chat or repeatedly retry a rate-limited refresh.
- Verified actual usage response `ok`: five-hour utilization 22%, seven-day utilization 56%. GUI real-data render assertions passed with `quota_cached=False`; restarted packaged window independently showed remaining 78% / 44%, green bars and no previous-value/update-failed state. Native PrintWindow capture verified the actual window; CopyFromScreen initially captured an unrelated foreground browser and was rejected as evidence.
- This project-specific recovery is recorded here rather than persisting account-authentication instructions in a personal skill.
- Numeric export utilities/tests remain for compatibility, but are no longer the default Claude acquisition path.
- Diagnostic probe source is untracked and no longer active. No input JSON/conversation/credentials were recorded by the probe.

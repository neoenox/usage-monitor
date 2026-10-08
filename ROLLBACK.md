# Local Claude acquisition rollback (2026-10-09)

At the user's request, restore the Claude direct acquisition implementation from 96a6895, while retaining subsequent Codex, cache validation, forecast, SQLite and native Unicode shortcut fixes.

- Temporary probe configuration removed from the active Claude settings.
- Original pre-export statusline restored using its backup, preserving unrelated settings.
- scan_claude now uses fetch_claude_oauth; statusline setup buttons removed.
- Model-based authentication recovery remains disabled.
- The earlier export-only security/distribution statements in README, DISTRIBUTION and ISSUE_VERIFICATION describe the prior merged redesign, not this local rollback. This rollback restores credential use and does not resolve the previously documented provider-policy concerns; it is not authorization for general distribution.
- Actual local direct acquisition returned `expired`, with no windows. Restoring the code does not establish restored live acquisition; official-tool reauthentication is still needed if credentials remain expired.
- Numeric export utilities/tests remain for compatibility, but are no longer the default Claude acquisition path.
- Diagnostic probe source is untracked and no longer active. No input JSON/conversation/credentials were recorded by the probe.

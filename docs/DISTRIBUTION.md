# Distribution and authentication constraints

Checked against official documentation on 2026-10-08. This is engineering guidance, not legal advice. Distribution approval is not implied by a successful local test.

## Codex

The [official app-server documentation](https://developers.openai.com/codex/app-server) documents `account/rateLimits/read` for ChatGPT rate limits. Keep authentication inside the installed official Codex binary and use local stdio; no model turn is needed.

The same documentation says local or open-source applications already using app-server authentication may continue, recommends migrating to Sign in with ChatGPT, and states: **“App-server authentication has never been permitted for commercial or hosted services.”**

Before commercial/hosted distribution, confirm eligibility and the [Sign in with ChatGPT](https://developers.openai.com/siwc) integration path. Do not assume that the existing-local-app exception covers every new distribution.

[API-key authentication](https://developers.openai.com/codex/auth) uses separate API pricing, not included ChatGPT plan credits. Do not label API billing as subscription quota. Quota windows may be null or absent, and example durations are not a fixed contract.

## Claude: do not distribute credential extraction as supported integration

[Anthropic's policy](https://code.claude.com/docs/en/legal-and-compliance#authentication-and-credential-use) states:

> developers may not collect, store, or intermediate Claude.ai credentials or session tokens

It also prohibits third-party developers offering Claude.ai login in their own apps or routing requests through users' Free/Pro/Max credentials. The exception for users signing into an unmodified official Claude Code binary is not permission to extract that binary's tokens into this monitor. No explicit read-only monitoring exception was found.

**Direct Claude OAuth polling is not cleared for general distribution. User consent alone does not establish provider permission.** The adapter has been retired: compatibility entry points are no-ops and neither credential reading nor network refresh is implemented. The monitor cannot consume model usage to recover credentials.

## Approved credential-free Claude integration

The [documented statusline interface](https://code.claude.com/docs/en/statusline#rate-limit-usage) supplies JSON to a user-configured script, including:

- `rate_limits.five_hour.used_percentage` and `resets_at`
- `rate_limits.seven_day.used_percentage` and `resets_at`

A local opt-in adapter can export only these numeric fields and observation timestamps. Do not capture credentials or transcripts; do not replace an existing statusline without explicit consent and a restore path.

Availability is limited: quota data appears only for eligible subscriptions/gateways and after an API response in the session. Windows can be absent independently and disappear after reset. This is event-driven observation, not independent always-live background polling. Retain last observed values with timestamps and mark stale/absent data honestly.

This documented interface is preferable to credential extraction, but it is not an explicit provider endorsement of this standalone monitor. [Authentication documentation](https://code.claude.com/docs/en/authentication) distinguishes subscription login from Console/API billing; `setup-token` does not waive third-party credential policy.

## Release gate

- [x] Replace direct Claude credential polling with user-approved numeric export. This approval is the user's implementation choice, not provider distribution approval.
- [x] Add provider setup guidance, consent, existing-statusline backup and uninstall/restore instructions.
- [x] Test synthetic missing-tool/error states, expired/missing windows, offline, restart and recovery. No real account expiry is forced and Claude authentication is intentionally not inspected.
- [x] Verify numeric whitelist and synthetic secret exclusion in quota cache and packaged export. No real credentials are used in these tests; this is not an exhaustive forensic scan of every local artifact.
- [ ] Confirm Codex eligibility for the intended local/open-source/commercial/hosted distribution.

Do not advertise the current build as ready for general commercial distribution.

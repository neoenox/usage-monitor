# Distribution and authentication constraints

Checked against official documentation on 2026-10-08; browser status-page path re-reviewed against primary sources on 2026-10-16; Codex eligibility re-reviewed against primary sources on 2026-10-18. This is engineering guidance, not legal advice. Distribution approval is not implied by a successful local test.

## Codex

The [official app-server documentation](https://developers.openai.com/codex/app-server) documents `account/rateLimits/read` for ChatGPT rate limits. Keep authentication inside the installed official Codex binary and use local stdio; no model turn is needed.

The same documentation says local or open-source applications already using app-server authentication may continue, recommends migrating to Sign in with ChatGPT, and states: **“App-server authentication has never been permitted for commercial or hosted services.”**

Before commercial/hosted distribution, confirm eligibility and the [Sign in with ChatGPT](https://developers.openai.com/siwc) integration path (see the review below). Do not assume that the existing-local-app exception covers every new distribution.

[API-key authentication](https://developers.openai.com/codex/auth) uses separate API pricing, not included ChatGPT plan credits. Do not label API billing as subscription quota. Quota windows may be null or absent, and example durations are not a fixed contract.

### Codex eligibility review (2026-10-18)

Re-read the primary sources for the intended scope (local, self-hosted, open-source; the user's own installed official Codex binary; local stdio; no model turn):

- The quoted restriction is still current, and the same page still says local or open-source applications using app-server authentication *can continue using it* — with a migration recommendation, not a revocation. That continuation is the basis for the current scope.
- `account/rateLimits/read` is still documented. The page now also describes a backward-compatible single-bucket `rateLimits` view, a multi-bucket `rateLimitsByLimitId` view keyed by metered `limit_id`, and an `account/rateLimits/updated` notification. The monitor's single-bucket use stays supported; the multi-bucket view is a possible future enhancement, not a requirement.
- `clientInfo.name` identifies the client for the OpenAI Compliance Logs Platform, and new Codex integrations intended for enterprise use must contact OpenAI to be added to a known-clients list. Enterprise deployment therefore needs an explicit provider step, not just this code.
- [Sign in with ChatGPT](https://developers.openai.com/siwc) documents ChatGPT-plan usage for open-source and locally hosted apps and publishes a self-hosted VM guide for an open-source app the user runs on their own machine; offering a *paid or remotely hosted* app instead requires the interest form (partner waitlist), not self-certification. The monitor sends no model turn, so SIWC is outside its current scope.

Outcome: eligibility **is confirmed** for the intended local / self-hosted / open-source scope. Commercial or hosted distribution is **not** cleared by this review and still needs the SIWC path plus a provider agreement. Re-check if the scope changes. This is a reading of published documentation, not legal advice, and is not an endorsement from OpenAI.

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

## Approved browser status-page observation

The separate Chrome extension path is also approved for local use. It runs in the user's own Chrome, signed into their own account, and reloads the usage settings page on a 5-minute alarm. It forwards only numeric utilization and reset values to a local host over Chrome native messaging: no cookies, credentials, or transcripts are read or stored, and nothing is sent off the machine. The extension never inspects authentication state beyond extension presence/enabled/disabled. This observes the user's own already-authenticated page rather than performing an independent provider-API poll.

Distribution choice: keep the in-GUI settings panel and the manual `chrome://extensions` load (no installer). The user's existing Claude Code statusline is backed up and restored; while the monitor is active its display is replaced by the numeric export, and `claude_setup.py` provides the restore path.

### Browser path primary-source review (2026-10-16)

Anthropic's [Consumer Terms of Service](https://www.anthropic.com/legal/consumer-terms) §3 restricts, for Claude.ai and consumer plans: crawling, scraping or otherwise harvesting data other than as permitted (§3(4)), and accessing the Services through automated or non-human means (bot, script) unless via an API key or where otherwise explicitly permitted (§3(7)). The [Legal and compliance](https://code.claude.com/docs/en/legal-and-compliance) page adds that Anthropic reserves the right to enforce these restrictions without prior notice.

The extension's background reload of `claude.ai/settings/usage` on a timer is automated access to the consumer web service, so it is **not cleared** under those terms. It remains a personal, at-your-own-risk convenience: it must not be presented as an official or provider-approved integration, and it must not be distributed as a supported feature for general use. This is an engineering reading of the published terms, not legal advice.

## Release gate

- [x] Replace direct Claude credential polling with user-approved numeric export. This approval is the user's implementation choice, not provider distribution approval.
- [x] Approve the browser status-page path (user's own logged-in page, numeric-only, local native-messaging host, no installer).
- [x] Add provider setup guidance, consent, existing-statusline backup and uninstall/restore instructions.
- [x] Test synthetic missing-tool/error states, expired/missing windows, offline, restart and recovery. No real account expiry is forced and Claude authentication is intentionally not inspected.
- [x] Verify numeric whitelist and synthetic secret exclusion in quota cache and packaged export. No real credentials are used in these tests; this is not an exhaustive forensic scan of every local artifact.
- [x] Review the browser status-page path against primary sources. Outcome: restricted — automated web-UI access is not permitted under Consumer ToS §3(4)/(7); personal use only, not distributed as official (see above).
- [x] Confirm Codex eligibility for the intended local/open-source/commercial/hosted distribution. Resolved 2026-10-18 for the intended scope: local, self-hosted and open-source use is consistent with the documented continuation for local/open-source app-server applications. Commercial or hosted distribution is not cleared by this project alone — it needs the SIWC path plus a provider agreement (see the Codex eligibility review).

## Distribution scope (current)

The project targets local, self-hosted and open-source use; that scope's Codex eligibility was confirmed against primary sources on 2026-10-18 (see the Codex eligibility review above). Commercial or hosted distribution is not cleared, and the current build must not be advertised as ready for general commercial distribution. The browser status-page path is a personal-use convenience only (see the primary-source review above) and must not be bundled as a supported integration in any distribution.

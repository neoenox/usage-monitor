"""Claude OAuth refresh backoff: don't hammer a rate-limited endpoint."""
from __future__ import annotations

import io
import json
import time
import urllib.error

import monitor as m


def _isolate_backoff(tmp_path, monkeypatch):
    local = tmp_path / "local"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    return local / "usage-monitor" / ".claude-refresh-backoff.json"


def test_refresh_429_records_backoff_and_skips_network(tmp_path, monkeypatch):
    backoff = _isolate_backoff(tmp_path, monkeypatch)
    calls = []

    def fail_429(req, timeout=10):
        calls.append(1)
        raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {}, io.BytesIO(b"{}"))

    monkeypatch.setattr(m.urllib.request, "urlopen", fail_429)
    assert m._refresh_oauth("refresh-token") == ""
    assert backoff.exists()
    assert m._refresh_backoff_active() is True
    # Second call inside cooldown must not touch the network.
    assert m._refresh_oauth("refresh-token") == ""
    assert len(calls) == 1


def test_refresh_success_clears_backoff(tmp_path, monkeypatch):
    backoff = _isolate_backoff(tmp_path, monkeypatch)

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"access_token": "new-token"}).encode()

    monkeypatch.setattr(m.urllib.request, "urlopen", lambda req, timeout=10: Resp())
    assert m._refresh_oauth("refresh-token") == "new-token"
    assert not backoff.exists()

    # A later failure recreates the marker, then success clears it again.
    def fail(req, timeout=10):
        raise urllib.error.HTTPError(req.full_url, 500, "boom", {}, io.BytesIO(b"{}"))

    monkeypatch.setattr(m.urllib.request, "urlopen", fail)
    assert m._refresh_oauth("refresh-token") == ""
    assert backoff.exists()
    monkeypatch.setattr(m.urllib.request, "urlopen", lambda req, timeout=10: Resp())
    # Force expiry of the short retry window by backdating the marker.
    raw = json.loads(backoff.read_text(encoding="utf-8"))
    raw["failed_at"] = time.time() - m.CLAUDE_REFRESH_RETRY_S - 1
    backoff.write_text(json.dumps(raw), encoding="utf-8")
    assert m._refresh_oauth("refresh-token") == "new-token"
    assert not backoff.exists()


def test_fetch_oauth_reports_cooldown_detail(tmp_path, monkeypatch):
    _isolate_backoff(tmp_path, monkeypatch)
    creds = tmp_path / ".claude" / ".credentials.json"
    creds.parent.mkdir(parents=True)
    creds.write_text(json.dumps({"claudeAiOauth": {
        "accessToken": "old", "refreshToken": "r",
        "expiresAt": int(time.time() * 1000) - 3600000,
    }}), encoding="utf-8")
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setattr(m, "claude_token_from_os_store", lambda: "")
    monkeypatch.setattr(m, "_refresh_oauth", lambda _: "")
    # No backoff yet: plain expired.
    assert m.fetch_claude_oauth(tmp_path) == {"status": "expired"}
    # With an active backoff marker, callers can tell why no retry happened.
    m._record_refresh_failure(True)
    out = m.fetch_claude_oauth(tmp_path)
    assert out["status"] == "expired"
    assert out["detail"] == "rate_limited_retry_later"


def test_corrupt_backoff_file_does_not_block(tmp_path, monkeypatch):
    backoff = _isolate_backoff(tmp_path, monkeypatch)
    backoff.parent.mkdir(parents=True, exist_ok=True)
    backoff.write_text("not json", encoding="utf-8")
    assert m._refresh_backoff_active() is False


def test_expired_guidance_points_to_official_relogin():
    import gui

    _, cl = gui.setup_guidance({"usage_status": "ok"},
                               {"oauth": {"status": "expired"}})
    assert "claude auth login --claudeai" in cl
    assert "連打" in cl

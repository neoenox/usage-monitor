"""E2E: offline start, restart with on-disk state and recovery (issue #37 / T4).

Covers the numeric Claude statusline/browser path (not just the Codex cache) and
asserts that last-known values are shown honestly and never as a fresh sample.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import claude_browser
import claude_export
import monitor as m
import usage_cache as cache

ROOT = Path(__file__).resolve().parent.parent


def _quota(five: float = 30.0, week: float = 40.0) -> dict:
    now = int(time.time())
    return {"rate_limits": {
        "five_hour": {"used_percentage": five, "resets_at": now + 3600},
        "seven_day": {"used_percentage": week, "resets_at": now + 86400}}}


def _snapshots(now: float):
    future = int(now) + 3600
    codex = {"has_rate": True, "usage_status": "ok", "rate_limits": {
        "primary": {"used_percent": 26, "resets_at": future},
        "secondary": {"used_percent": 21, "resets_at": future}}}
    claude = {"quota_source": "statusline", "oauth": {
        "status": "ok",
        "five_hour": {"utilization": 30, "resets_at": "2999-01-01T00:00:00Z"},
        "seven_day": {"utilization": 40, "resets_at": "2999-01-01T00:00:00Z"}}}
    return codex, claude


def test_statusline_path_offline_corruption_and_recovery(fake_home):
    """No file -> missing; numeric export -> ok; corrupt -> missing; restored -> ok."""
    target = claude_export.path(fake_home)
    assert m.scan_claude(fake_home)["oauth"]["status"] == "missing_token"

    claude_export.export(_quota(five=30.0), target)
    claude = m.scan_claude(fake_home)
    assert claude["oauth"]["status"] == "ok"
    assert claude["quota_source"] == "statusline"
    assert claude["oauth"]["five_hour"]["utilization"] == 30.0
    assert claude["observed_at"] and claude["observed_at"] > 0

    target.write_text("not json", encoding="utf-8")
    broken = m.scan_claude(fake_home)
    assert broken["oauth"]["status"] == "missing_token"
    assert broken["observed_at"] is None

    claude_export.export(_quota(five=55.0), target)
    recovered = m.scan_claude(fake_home)
    assert recovered["oauth"]["status"] == "ok"
    assert recovered["oauth"]["five_hour"]["utilization"] == 55.0


def test_browser_file_newer_than_statusline_wins(fake_home):
    """The freshest observation wins, regardless of which path wrote it."""
    now = int(time.time())
    claude_export.export(_quota(five=10.0), claude_export.path(fake_home), now=now - 100)
    claude_export.export(_quota(five=90.0), claude_browser.path(fake_home), now=now)

    claude = m.scan_claude(fake_home)
    assert claude["quota_source"] == "browser"
    assert claude["oauth"]["five_hour"]["utilization"] == 90.0


def test_statusline_source_is_not_duplicated_into_cache(tmp_path):
    """Export sources persist in their own quota file; the cache must not copy them.

    Restart retention for the numeric path is therefore file-based (see the
    round-trip test above), not cache-based.
    """
    path = tmp_path / "last-usage.json"
    codex, claude = _snapshots(now=1000)
    codex, claude = cache.apply(codex, claude, path, now=1000)

    assert not claude.get("quota_cached")
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert "claude" not in saved


def test_offline_restart_retains_legacy_cached_quota(tmp_path):
    """A previously cached sample is served with its original timestamp when offline."""
    path = tmp_path / "last-usage.json"
    codex, claude = _snapshots(now=1000)
    claude.pop("quota_source")  # legacy cache format (no export source)
    cache.apply(codex, claude, path, now=1000)

    codex, claude = cache.apply({"has_rate": False, "usage_status": "error"},
                                {"oauth": {"status": "error"}}, path, now=1060)
    assert codex["has_rate"] and codex["quota_cached"] and codex["observed_at"] == 1000
    assert claude["quota_cached"] and claude["observed_at"] == 1000
    assert claude["oauth"]["five_hour"]["utilization"] == 30.0


def test_corrupt_cache_is_unavailable_without_error(tmp_path):
    """A corrupt last-usage cache must degrade to unavailable, never raise."""
    path = tmp_path / "last-usage.json"
    path.write_text("broken", encoding="utf-8")

    codex, claude = cache.apply({"has_rate": False, "usage_status": "error"},
                                {"oauth": {"status": "error"}}, path)
    assert not codex.get("has_rate") and not codex.get("quota_cached")
    assert claude["oauth"]["status"] == "error"


def test_cli_restart_reports_quota_with_corrupt_cache_present(fake_home, tmp_path):
    """Real subprocess restart: on-disk quota is reported even beside a corrupt cache."""
    claude_export.export(_quota(five=30.0), claude_export.path(fake_home))
    appdata = tmp_path / "appdata"
    appdata.mkdir()
    (appdata / "last-usage.json").write_text("broken", encoding="utf-8")

    env = {"PATH": os.environ["PATH"],
           "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
           "LOCALAPPDATA": str(appdata)}
    proc = subprocess.run(
        [sys.executable, str(ROOT / "monitor.py"), "--json", "--home", str(fake_home)],
        capture_output=True, text=True, timeout=120, env=env)
    assert proc.returncode == 0, proc.stderr[-500:]
    data = json.loads(proc.stdout)
    assert data["claude"]["oauth"]["status"] == "ok"
    assert data["claude"]["oauth"]["five_hour"]["utilization"] == 30.0

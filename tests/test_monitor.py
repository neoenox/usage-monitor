"""monitor.py 単体テスト。"""
from __future__ import annotations

import json
import time
import urllib.request

import monitor as m


def test_fmt_num():
    assert m.fmt_num(1234567) == "1,234,567"


def test_fmt_countdown_future():
    assert m.fmt_countdown(int(time.time()) + 3700).startswith("あと1時間")


def test_fmt_countdown_days():
    assert m.fmt_countdown(int(time.time()) + 4 * 86400 + 2 * 3600 + 30 * 60 + 5) == "あと4日2時間30分"
    assert m.fmt_countdown(int(time.time()) + 25 * 3600 + 120).startswith("あと1日1時間")


def test_project_hit_window_linear():
    now = int(time.time())
    reset = now + 3600  # 5h窓の残り1h
    start = reset - 300 * 60
    # 窓開始から50%使った → 100%は窓終了後=セーフ扱い(None)
    used = 50.0 * (now - start) / (300 * 60)
    assert m.project_hit(used, 300, reset) is None
    # 激しく使って窓内に枯渇する pace
    hit = m.project_hit(90.0, 300, reset)
    assert hit is not None and hit < reset


def test_project_hit_history_slope():
    now = int(time.time())
    reset = now + 5 * 3600
    hist = [(now - 3600, 10.0), (now - 1800, 20.0), (now, 30.0)]
    hit = m.project_hit(30.0, 10080, reset, hist)
    assert hit is not None and hit < reset  # 20%/h → 残70%は3.5h後 < 残5h
    # 使用ゼロ/減少ならNone
    assert m.project_hit(0.0, 10080, reset, [(now - 3600, 5.0), (now, 5.0)]) is None


def test_pace_label():
    assert m.pace_label(0, 300, None) == "このペースならセーフ"
    lbl = m.pace_label(90.0, 300, int(time.time()) + 3600)
    assert "枯渇" in lbl


def test_week_pace():
    now = int(time.time())
    # 週窓の半分経過で使用80% → over
    reset = now + 7 * 86400 // 2
    assert m.week_pace(80.0, 10080, reset).startswith("over pace")
    # 半分経過で使用10% → under
    assert m.week_pace(10.0, 10080, reset).startswith("under pace")
    # 半分経過で使用50% → on
    assert m.week_pace(50.0, 10080, reset).startswith("on pace")
    assert m.week_pace(None, 10080, reset) == "-"


def test_fmt_countdown_invalid():
    assert m.fmt_countdown(None) == "-"
    assert m.fmt_countdown("xx") == "-"


def test_scan_codex_sums_last_per_file(codex_data):
    assert codex_data["files"] == 2
    assert codex_data["sessions_with_tokens"] == 2
    assert codex_data["input"] == 3000 + 5000
    assert codex_data["output"] == 300 + 500


def test_scan_codex_latest_rate(codex_data):
    rl = codex_data["rate_limits"]
    # mtime最新ファイルの最終イベントが採用される (どちらも同値系なので50/40のはず)
    assert rl["primary"]["used_percent"] in (30.0, 50.0)
    assert rl["secondary"]["used_percent"] in (20.0, 40.0)


def test_scan_claude_local(claude_data):
    assert claude_data["files"] == 1
    assert claude_data["messages"] == 1
    assert claude_data["input"] == 10
    assert claude_data["oauth"]["status"] == "missing_token"


def test_fetch_oauth_ok(monkeypatch):
    payload = {"five_hour": {"utilization": 31.0, "resets_at": "2026-09-29T15:39:00+00:00"},
               "seven_day": {"utilization": 5.0, "resets_at": "2026-10-06T06:00:00+00:00"}}

    class FakeRes:
        def read(self):
            return json.dumps(payload).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: FakeRes())
    import pathlib

    out = m.fetch_claude_oauth(pathlib.Path("/nonexistent"))
    # token解決: envもfileも無いのでmissingのはず → envを仮設定して再試行
    assert out["status"] == "missing_token"
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "dummy")
    out = m.fetch_claude_oauth(pathlib.Path("/nonexistent"))
    assert out["status"] == "ok"
    assert out["five_hour"]["utilization"] == 31.0


def test_expired_status(tmp_path, monkeypatch):
    """期限切れ資格情報 → CLI再取得が不発なら expired (未設定と区別)。"""
    import json as _json
    import time as _time

    creds = tmp_path / ".claude" / ".credentials.json"
    creds.parent.mkdir(parents=True)
    creds.write_text(_json.dumps({"claudeAiOauth": {
        "accessToken": "old", "refreshToken": "r",
        "expiresAt": int(_time.time() * 1000) - 3600_000}}), encoding="utf-8")
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setattr(m, "_cli_refresh_creds", lambda home: False)
    monkeypatch.setattr(m, "_refresh_oauth", lambda refresh: "")
    out = m.fetch_claude_oauth(tmp_path)
    assert out["status"] == "expired"
    assert m.claude_has_creds(tmp_path) is True

def test_custom_home_does_not_use_real_credentials_or_network(tmp_path, monkeypatch):
    """A synthetic HOME must stay isolated from this machine's auth state."""
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "real-machine-token")

    def unexpected_os_store():
        raise AssertionError("OS credential store must not be read for a custom HOME")

    def unexpected_network(*args, **kwargs):
        raise AssertionError("live usage API must not be called for a custom HOME")

    monkeypatch.setattr(m, "claude_token_from_os_store", unexpected_os_store)
    monkeypatch.setattr(urllib.request, "urlopen", unexpected_network)

    out = m.scan_claude(tmp_path)
    assert out["oauth"]["status"] == "missing_token"


def test_cli_refresh_failure_does_not_start_cooldown(tmp_path, monkeypatch):
    import shutil
    import subprocess
    from types import SimpleNamespace

    local = tmp_path / "local"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.setattr(shutil, "which", lambda name: "claude.exe")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1),
    )

    assert m._cli_refresh_creds(tmp_path) is False
    assert not (local / "usage-monitor" / ".cli_refresh").exists()


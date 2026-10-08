"""monitor.py 単体テスト。"""
from __future__ import annotations

import json
import time
import urllib.request

import pytest

import monitor as m


def test_fmt_num():
    assert m.fmt_num(1234567) == "1,234,567"


def test_version():
    import re as _re

    assert _re.fullmatch(r"\d+\.\d+\.\d+", m.__version__), m.__version__


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
    import re as _re

    assert m.pace_label(0, 300, None) == "このペースならセーフ"
    lbl = m.pace_label(90.0, 300, int(time.time()) + 3600)
    assert "枯渇" in lbl
    lbl_nodate = m.pace_label(90.0, 300, int(time.time()) + 3600, (), False)
    assert _re.fullmatch(r"このままだと\d{2}:\d{2}頃枯渇", lbl_nodate), lbl_nodate


def test_week_pace():
    now = int(time.time())    # 週窓の半分経過で使用80% → over
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


def test_week_budget():
    now = int(time.time())
    reset = now + 4 * 86400  # 残り4日
    assert m.week_budget(40.0, reset) == "1日15%まで"  # 残り60%/4日
    assert m.week_budget(None, reset) == "-"
    assert m.week_budget(40.0, None) == "-"
    assert m.week_budget(100.0, reset) == "予算なし(上限到達)"
    assert m.week_budget(40.0, now - 10) == "まもなくリセット"
    # 残り1日未満はキープ表示
    assert m.week_budget(90.0, now + 12 * 3600) == "残り10%をキープ"


def test_week_status_has_no_short_term_forecast():
    now = int(time.time())
    reset = now + 4 * 86400
    s = m.week_status(40.0, reset)
    assert "枯渇" not in s and "セーフ" not in s
    assert "pace" in s and "1日" in s


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

def test_unlinked_home(tmp_path):
    """空HOME: has_rate False・tooltipは未連携表示。"""
    import gui

    codex = m.scan_codex(tmp_path)
    assert codex["files"] == 0 and codex["has_rate"] is False
    tip = gui.tray_tooltip(codex, {"oauth": {"status": "missing_token"}})
    assert "Codex 使用量未取得" in tip


def test_newest_event_wins_over_mtime(tmp_path):
    """交互追記される複数セッションでも最新イベントを採用 (回帰)。"""
    import json as _json
    import os as _os

    def ev(ts, p, s):
        return _json.dumps({"timestamp": ts, "type": "event_msg", "payload": {
            "type": "token_count",
            "info": {"total_token_usage": {"input_tokens": 1, "output_tokens": 1,
                                           "cached_input_tokens": 0}},
            "rate_limits": {"limit_id": "codex", "plan_type": "plus",
                            "primary": {"used_percent": p, "window_minutes": 300,
                                        "resets_at": 1790763214},
                            "secondary": {"used_percent": s, "window_minutes": 10080,
                                          "resets_at": 1791070697}}}})
    d = tmp_path / ".codex" / "sessions"
    d.mkdir(parents=True)
    old = d / "old-mtime.jsonl"  # mtimeは古いがイベントは新しい
    new = d / "new-mtime.jsonl"  # mtimeは新しいがイベントは古い
    old.write_text(ev("2026-09-30T06:17:00.000Z", 99.0, 54.0) + "\n", encoding="utf-8")
    new.write_text(ev("2026-09-29T10:00:00.000Z", 0.0, 3.0) + "\n", encoding="utf-8")
    _os.utime(new, (1790720000, 1790720000))  # mtimeを新しく偽装
    out = m.scan_codex(tmp_path)
    assert out["rate_limits"]["primary"]["used_percent"] == 99.0
    assert out["rate_limits"]["secondary"]["used_percent"] == 54.0


def test_rate_limit_timestamps_use_instant_order(tmp_path):
    """ISO offsets must not change which rate-limit event is newest."""
    import json as _json

    folder = tmp_path / ".codex" / "sessions"
    folder.mkdir(parents=True)

    def rate_event(ts, used):
        return _json.dumps({
            "timestamp": ts,
            "type": "event_msg",
            "payload": {"rate_limits": {"primary": {"used_percent": used}}},
        })

    # 09:00+02:00 is 07:00 UTC and is older than 08:00Z.
    # Lexicographic comparison incorrectly chooses the first timestamp.
    (folder / "a.jsonl").write_text(
        rate_event("2026-09-30T08:00:00Z", 80.0) + "\n",
        encoding="utf-8",
    )
    (folder / "b.jsonl").write_text(
        rate_event("2026-09-30T09:00:00+02:00", 10.0) + "\n"
        + rate_event("not-an-iso-timestamp", 99.0) + "\n"
        + _json.dumps({"type": "event_msg", "payload": {
            "rate_limits": {"primary": {"used_percent": 5.0}},
        }}) + "\n",
        encoding="utf-8",
    )
    result = m.scan_codex(tmp_path)
    assert result["rate_limits"]["primary"]["used_percent"] == 80.0
    assert result["rate_source"] == "a.jsonl"


def test_rate_limit_without_timestamp_keeps_legacy_fallback(tmp_path):
    """Undated events still provide a fallback if there are no dated ones."""
    import json as _json

    folder = tmp_path / ".codex" / "sessions"
    folder.mkdir(parents=True)
    def event(used):
        return _json.dumps({"type": "event_msg", "payload": {
            "rate_limits": {"primary": {"used_percent": used}},
        }})
    (folder / "a.jsonl").write_text(event(10) + "\n" + event(20) + "\n", encoding="utf-8")
    result = m.scan_codex(tmp_path)
    assert result["rate_limits"]["primary"]["used_percent"] == 20


def test_is_stale():
    import time as _time

    assert m.is_stale(int(_time.time()) - 10) is True
    assert m.is_stale(int(_time.time()) + 3600) is False
    assert m.is_stale(None) is False


def test_normalize_snapshot():
    import time as _time

    past, future = int(_time.time()) - 3600, int(_time.time()) + 3600
    codex = {"rate_limits": {
        "primary": {"used_percent": 99.0, "resets_at": past},
        "secondary": {"used_percent": 30.0, "resets_at": future}}}
    claude = {"oauth": {"status": "ok",
                        "five_hour": {"utilization": 50.0,
                                      "resets_at": "2000-01-01T00:00:00+00:00"},
                        "seven_day": {"utilization": 10.0,
                                      "resets_at": "2999-01-01T00:00:00+00:00"}}}
    cx, cl = m.normalize_snapshot(codex, claude)
    assert cx["rate_limits"]["primary"]["used_percent"] == 99.0
    assert cx["has_rate"] is False
    assert cx["usage_status"] == "stale"
    assert cx["rate_limits"]["secondary"]["used_percent"] == 30.0
    assert "new_window_wk" not in cx
    assert cl["oauth"]["five_hour"]["utilization"] == 0.0
    assert cl["new_window_5h"] is True
    assert cl["oauth"]["seven_day"]["utilization"] == 10.0
    # 元dictは不変
    assert codex["rate_limits"]["primary"]["used_percent"] == 99.0


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


@pytest.fixture()
def local_zone(monkeypatch):
    """Use real TZ conversion on POSIX, and IANA rules on Windows."""
    import os
    from datetime import datetime
    from zoneinfo import ZoneInfo

    if hasattr(time, "tzset"):
        original = os.environ.get("TZ")

        def select(name):
            monkeypatch.setenv("TZ", name)
            time.tzset()

        yield select
        if original is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = original
        time.tzset()
    else:
        def select(name):
            zone = ZoneInfo(name)

            def localtime(timestamp):
                return datetime.fromtimestamp(timestamp, zone).timetuple()

            def mktime(parts):
                value = datetime(*parts[:6], tzinfo=zone)
                if parts[8] != -1:
                    # Preserve explicit DST hints to reproduce the old bug.
                    from datetime import timedelta, timezone
                    standard = value.utcoffset() - value.dst()
                    value = value.replace(tzinfo=timezone(
                        standard + timedelta(hours=parts[8])))
                return value.timestamp()

            monkeypatch.setattr(time, "localtime", localtime)
            monkeypatch.setattr(time, "mktime", mktime)

        yield select


@pytest.mark.parametrize("zone,now,days_ago,start_iso,end_iso,hours", [
    ("America/New_York", "2026-03-08T12:00:00-04:00", 0,
     "2026-03-08T00:00:00-05:00", "2026-03-09T00:00:00-04:00", 23),
    ("America/New_York", "2026-11-01T12:00:00-05:00", 0,
     "2026-11-01T00:00:00-04:00", "2026-11-02T00:00:00-05:00", 25),
    ("America/New_York", "2026-03-09T00:30:00-04:00", 1,
     "2026-03-08T00:00:00-05:00", "2026-03-09T00:00:00-04:00", 23),
    ("America/New_York", "2026-11-01T23:30:00-05:00", 1,
     "2026-10-31T00:00:00-04:00", "2026-11-01T00:00:00-04:00", 24),
    ("Asia/Tokyo", "2026-03-01T00:30:00+09:00", 1,
     "2026-02-28T00:00:00+09:00", "2026-03-01T00:00:00+09:00", 24),
    ("Asia/Tokyo", "2026-01-01T00:30:00+09:00", 1,
     "2025-12-31T00:00:00+09:00", "2026-01-01T00:00:00+09:00", 24),
    ("Asia/Tokyo", "2026-03-02T12:00:00+09:00", 2,
     "2026-02-28T00:00:00+09:00", "2026-03-01T00:00:00+09:00", 24),
])
def test_day_bounds(local_zone, monkeypatch, zone, now, days_ago,
                    start_iso, end_iso, hours):
    from datetime import datetime

    local_zone(zone)
    monkeypatch.setattr(time, "time", lambda: datetime.fromisoformat(now).timestamp())
    start, end = m.day_bounds(days_ago)
    assert start == int(datetime.fromisoformat(start_iso).timestamp())
    assert end == int(datetime.fromisoformat(end_iso).timestamp())
    assert end - start == hours * 3600
    assert time.localtime(start)[3:6] == (0, 0, 0)
    assert time.localtime(end)[3:6] == (0, 0, 0)
    # Include the day's last second, but exclude the next midnight.
    assert m.daily_max_used([(start - 1, 99), (start, 10),
                             (end - 1, 80), (end, 100)], start, end) == 80


def test_daily_max_used():
    pts = [(100, 10.0), (200, 90.0), (300, 50.0)]
    assert m.daily_max_used(pts, 150, 250) == 90.0
    assert m.daily_max_used(pts, 400, 500) is None


def test_daily_report_lines():
    lines = m.daily_report_lines(
        {"codex_5h": 99.0, "codex_wk": 54.0, "claude_5h": None, "claude_wk": 11.0},
        {"codex_wk": "on pace (経過47%/使用54%)"})
    assert "Codex 5h最大99%" in lines[0]
    assert "Claude 5h-" in lines[0]
    assert any("Codex週" in ln and "on pace" in ln for ln in lines)


def test_expired_file_can_fall_back_to_os_store(tmp_path, monkeypatch):
    creds = tmp_path / ".claude" / ".credentials.json"
    creds.parent.mkdir()
    creds.write_text(json.dumps({"claudeAiOauth": {
        "accessToken": "old", "refreshToken": "r",
        "expiresAt": int(time.time() * 1000) - 3600000,
    }}), encoding="utf-8")
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setattr(m, "_refresh_oauth", lambda _: "")
    monkeypatch.setattr(m, "_cli_refresh_creds", lambda _: False)
    monkeypatch.setattr(m, "claude_token_from_os_store", lambda: "os-token")
    assert m.claude_token(tmp_path) == "os-token"


def test_non_windows_credential_lookup_is_safe():
    import os
    import pytest
    if os.name == "nt":
        pytest.skip("Windows requires a Credential Manager integration test")
    assert m.claude_token_from_os_store() == ""
    assert m._read_credential_store("nope") == ""

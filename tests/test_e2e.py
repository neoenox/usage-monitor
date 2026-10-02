"""E2Eテスト: CLI実プロセス / GUI描画 / トレイクリック配送。"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_cli_json_e2e(fake_home, tmp_path):
    """monitor.py を別プロセスで実行しJSON出力を検証。"""
    proc = subprocess.run(
        [sys.executable, str(ROOT / "monitor.py"), "--json", "--home", str(fake_home)],
        capture_output=True, text=True, timeout=120,
        env={"PATH": __import__("os").environ["PATH"], "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", "")},
    )
    assert proc.returncode == 0, proc.stderr[-500:]
    data = json.loads(proc.stdout)
    assert data["codex"]["input"] == 8000
    assert data["claude"]["messages"] == 1
    assert data["claude"]["oauth"]["status"] == "missing_token"


def test_gui_render_e2e(app, fake_home):
    """実Tkウィンドウに描画しラベル/バー/グラフを検証 (共有ルート)。"""
    import history as h
    import monitor as m

    h.record({"codex_5h": 50.0, "claude_5h": 10.0})
    codex = m.scan_codex(fake_home)
    claude = m.scan_claude(fake_home)
    import time as _time

    future = int(_time.time()) + 3600
    codex["rate_limits"]["primary"]["resets_at"] = future
    codex["rate_limits"]["secondary"]["resets_at"] = future
    app._render(codex, claude)
    app.update_idletasks()
    assert "残り" in app.lbl5.cget("text")
    used = float(codex["rate_limits"]["primary"]["used_percent"])
    assert float(app.bar5["value"]) == pytest.approx(100 - used)
    assert len(app.chart.find_all()) > 0


def test_tray_click_e2e():
    """実トレイアイコンに合成クリックを送り open 配送を検証 (バルーン1発表示)。"""
    sys.path.insert(0, str(ROOT))
    import tray_win32
    from tray_win32 import WM_TRAY, WM_LBUTTONUP

    calls: list[str] = []
    tray = tray_win32.Win32Tray(
        "e2e test",
        on_open=lambda: calls.append("open"),
        on_refresh=lambda: calls.append("refresh"),
        on_quit=lambda: calls.append("quit"),
    )
    th = tray_win32.run_threaded(tray)
    try:
        time.sleep(1)
        tray.set_tooltip("e2e tooltip")
        tray.balloon("E2Eテスト", "通知パスの確認（無害）")
        assert tray_win32.user32.PostMessageW(tray.hwnd, WM_TRAY, 0, WM_LBUTTONUP)
        deadline = time.time() + 5
        while "open" not in calls and time.time() < deadline:
            time.sleep(0.1)
        assert "open" in calls
    finally:
        tray.stop()
        th.join(timeout=5)
        assert not th.is_alive()


def test_debug_log_rotation(tmp_path):
    """tray-debug.logは上限行で切り詰められる。"""
    import tray_win32

    p = tmp_path / "tray-debug.log"
    p.write_text("\n".join(f"line {i}" for i in range(500)) + "\n", encoding="utf-8")
    # 64KB未満は触らない
    tray_win32._rotate_debug_log(p)
    assert len(p.read_text(encoding="utf-8").splitlines()) == 500
    p.write_bytes(b"x" * (64 * 1024 + 10) + b"\nline\n")
    tray_win32._rotate_debug_log(p)
    assert len(p.read_text(encoding="utf-8", errors="ignore").splitlines()) <= 200

    entries = [f"{i}: ログメッセージ " + "x" * 150 for i in range(500)]
    p.write_text("\n".join(entries) + "\n", encoding="utf-8")
    tray_win32._rotate_debug_log(p)
    assert p.read_text(encoding="utf-8").splitlines() == entries[-200:]


class _FakeTray:
    def __init__(self):
        self.balloons: list[tuple[str, str, bool]] = []

    def set_tooltip(self, text):
        pass

    def set_icon(self, path):
        pass

    def balloon(self, title, msg, warn=False):
        self.balloons.append((title, msg, warn))


def _low_codex():
    return {"has_rate": True, "rate_limits": {
        "primary": {"used_percent": 95.0, "window_minutes": 300, "resets_at": 1999999999},
        "secondary": {"used_percent": 10.0, "window_minutes": 10080, "resets_at": 1999999999}}}


def test_alert_integration_dedupe_and_rearm():
    """残量低下→バルーン1発・重複なし・回復で再武装 (Tk不要)。"""
    import gui

    ctl = gui.TrayController.__new__(gui.TrayController)
    ctl.notified = {}
    fake = _FakeTray()
    ctl.tray = fake
    claude = {"oauth": {"status": "missing_token"}}
    ctl._check_alerts(_low_codex(), claude)
    assert len(fake.balloons) == 1
    assert "要節約" in fake.balloons[0][0] and "Codex 5h" in fake.balloons[0][1]
    ctl._check_alerts(_low_codex(), claude)
    assert len(fake.balloons) == 1  # 同一閾値で再通知しない
    healthy = {"has_rate": True, "rate_limits": {
        "primary": {"used_percent": 50.0, "window_minutes": 300, "resets_at": 1999999999},
        "secondary": {"used_percent": 10.0, "window_minutes": 10080, "resets_at": 1999999999}}}
    ctl._check_alerts(healthy, claude)
    assert ctl.notified.get("Codex 5h") is None  # 25%超でリセット
    ctl._check_alerts(_low_codex(), claude)
    assert len(fake.balloons) == 2  # 再武装後に再通知


def test_gui_oauth_ok_and_stale_labels(app):
    """oauth正常系の描画＋stale注記の描画 (共有ルート)。"""
    claude_ok = {"files": 1, "messages": 1, "input": 1, "output": 2,
                 "cache_creation": 0, "cache_read": 0, "total": 3,
                 "oauth": {"status": "ok",
                           "five_hour": {"utilization": 20.0,
                                         "resets_at": "2999-01-01T00:00:00+00:00"},
                           "seven_day": {"utilization": 10.0,
                                         "resets_at": "2999-01-08T00:00:00+00:00"},
                           "seven_day_opus": {}, "seven_day_sonnet": {}}}
    codex = {"files": 1, "sessions_with_tokens": 1, "input": 1, "output": 1,
             "cached": 0, "total": 2, "has_rate": True,
             "rate_limits": {
                 "primary": {"used_percent": 10.0, "window_minutes": 300,
                             "resets_at": 2999999999},
                 "secondary": {"used_percent": 20.0, "window_minutes": 10080,
                               "resets_at": 2999999999}},
             "context": {"input": 1, "window": 100, "pct": 1.0}}
    app._render(codex, claude_ok)
    app.update_idletasks()
    assert "残り80%" in app.cl_lbl5.cget("text")
    assert "セーフ" in app.cl_lbl5.cget("text")
    # stale: リセット時刻が過去なら新窓扱いになる
    codex["rate_limits"]["primary"]["resets_at"] = 1000000000
    app._render(codex, claude_ok)
    app.update_idletasks()
    assert "新窓" in app.lbl5.cget("text")
    assert "残り100%" in app.lbl5.cget("text")


def test_daily_report_once_per_day(tmp_path, monkeypatch):
    """初回更新で前日レポート1発・同日2回目は出さない。"""
    import time as _time

    import gui
    import history as h
    import monitor as m

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    hist_db = tmp_path / "hist.db"
    start, _ = m.day_bounds(1)
    h.record({"codex_5h": 99.0, "codex_wk": 54.0}, path=hist_db, ts=start + 3600)
    real_recent = h.recent
    monkeypatch.setattr(
        h, "recent",
        lambda metric, hours=72: real_recent(metric, hours=hours, path=hist_db))

    ctl = gui.TrayController.__new__(gui.TrayController)
    ctl.notified = {}
    fake = _FakeTray()
    ctl.tray = fake
    codex = {"has_rate": True, "rate_limits": {
        "primary": {"used_percent": 1.0, "window_minutes": 300,
                     "resets_at": int(_time.time()) + 3600},
        "secondary": {"used_percent": 54.0, "window_minutes": 10080,
                      "resets_at": int(_time.time()) + 86400}}}
    claude = {"oauth": {"status": "missing_token"}}
    ctl._maybe_daily_report(codex, claude)
    assert len(fake.balloons) == 1
    assert "Codex 5h最大99%" in fake.balloons[0][1]
    ctl._maybe_daily_report(codex, claude)
    assert len(fake.balloons) == 1  # 同日は再通知しない


def test_overview_scroll_reaches_last_quota(app):
    app.deiconify()
    app.geometry("520x640")
    for label in (app.lbl5, app.lblW, app.cl_lbl5, app.cl_lblW):
        label.config(text="5h 残り80% (使用20%) reset=14:00 (4時間) [余裕あり]")
    app.update()
    app.overview_canvas.yview_moveto(1.0)
    app.update()
    bottom = app.cl_barW.winfo_rooty() + app.cl_barW.winfo_height()
    viewport_bottom = app.overview_canvas.winfo_rooty() + app.overview_canvas.winfo_height()
    assert bottom <= viewport_bottom
    assert app.lbl5.value.cget("text") == "残り 80%"
    app.withdraw()

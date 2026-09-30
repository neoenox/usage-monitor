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


def test_gui_render_e2e(fake_home, tmp_path, monkeypatch):
    """実Tkウィンドウに描画しラベル/バー/グラフを検証。"""
    import gui
    import history as h

    monkeypatch.setattr(h, "db_path", lambda: tmp_path / "hist.db")
    monkeypatch.setattr(gui.App, "refresh", lambda self: None)
    h.record({"codex_5h": 50.0, "claude_5h": 10.0})

    import monitor as m

    app = gui.App()
    try:
        app.withdraw()
        codex = m.scan_codex(fake_home)
        claude = m.scan_claude(fake_home)
        app._render(codex, claude)
        app.update_idletasks()
        assert "残り" in app.lbl5.cget("text")
        used = float(codex["rate_limits"]["primary"]["used_percent"])
        assert float(app.bar5["value"]) == pytest.approx(100 - used)
        assert len(app.chart.find_all()) > 0
    finally:
        app.destroy()


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

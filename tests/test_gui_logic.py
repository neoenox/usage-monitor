from __future__ import annotations

import subprocess

import gui


def test_set_autostart_preserves_source_mode_tray_arg(tmp_path, monkeypatch):
    captured = {}

    monkeypatch.setattr(gui, "startup_dir", lambda: tmp_path)
    monkeypatch.setattr(
        gui,
        "autostart_target",
        lambda: [r"C:\Python311\python.exe", r"C:\repo\gui.py", "--tray"],
    )

    import windows_shortcut
    monkeypatch.setattr(windows_shortcut, 'create', lambda *args: captured.update(args=args))
    assert gui.set_autostart(True) is True
    assert r"C:\repo\gui.py" in captured['args'][2]
    assert '--tray' in captured['args'][2]


def test_schedule_tick_cancels_previous_job():
    class Dummy:
        def __init__(self):
            self._tick_job = "old"
            self.cancelled = []
            self.scheduled = []

        def after_cancel(self, job):
            self.cancelled.append(job)

        def after(self, delay, callback):
            self.scheduled.append((delay, callback))
            return "new"

        def _tick(self):
            pass

    dummy = Dummy()
    gui.App._schedule_tick(dummy)

    assert dummy.cancelled == ["old"]
    assert len(dummy.scheduled) == 1
    assert dummy.scheduled[0][0] == 60_000
    assert dummy._tick_job == "new"


def test_refresh_ignores_overlapping_request(monkeypatch):
    class Dummy:
        _loading = True
    def unexpected(*args, **kwargs):
        raise AssertionError("Overlapping refresh started")
    monkeypatch.setattr(gui.threading, "Thread", unexpected)
    gui.App.refresh(Dummy())


def test_tick_auto_refreshes_even_without_codex_data(monkeypatch):
    import time
    class Label:
        def config(self, **kwargs): pass
    class Dummy:
        _updated_at = 0
        _last = ({"has_rate": False}, {})
        freshness = Label()
        refreshed = scheduled = 0
        def refresh(self): self.refreshed += 1
        def _schedule_tick(self): self.scheduled += 1
    monkeypatch.setattr(time, "monotonic", lambda: 301)
    obj = Dummy()
    gui.App._tick(obj)
    assert obj.refreshed == 1
    assert obj.scheduled == 1


def test_remaining_text_separates_value_and_reset():
    value, detail = gui.remaining_text("5h 残り80% (使用20%) reset=12:00 (1時間) [余裕あり]")
    assert value == "残り 80%"
    assert detail == "リセット：12:00 (1時間)\n予測：余裕あり"


def test_remaining_text_preserves_unavailable_reason():
    assert gui.remaining_text("未連携: ログインしてください") == ("", "未連携: ログインしてください")


def test_quota_state_uses_configured_thresholds():
    cfg = {"warn_at": 30, "crit_at": 15}
    assert gui.quota_state(31, cfg)[0] == "余裕あり"
    assert gui.quota_state(30, cfg)[0] == "注意"
    assert gui.quota_state(15, cfg)[0] == "残量わずか"
    assert gui.quota_state(0, cfg)[0] == "残量わずか"


def test_freshness_uses_completed_update_age():
    assert gui.freshness_text(59) == "最終更新：たった今"
    assert gui.freshness_text(60) == "最終更新：1分前"
    assert gui.freshness_text(121) == "最終更新：2分前"


def test_quota_forecast_requires_same_window_history(monkeypatch):
    import time
    monkeypatch.setattr(time, "time", lambda: 20000)
    assert gui.quota_forecast(20, 300, 25000) == "履歴不足で予測できません"
    assert gui.quota_forecast(20, 300, None) == "データ不足で予測できません"
    assert gui.quota_forecast(20, 300, 25000, [(1000, 0), (20000, 20)]) == "履歴不足で予測できません"
    assert gui.quota_forecast(20, 300, 25000, [(19700, 10), (20000, 20)]) == "履歴不足で予測できません"


def test_quota_forecast_distinguishes_safe_and_exhaustion(monkeypatch):
    import time
    monkeypatch.setattr(time, "time", lambda: 20000)
    assert gui.quota_forecast(20, 300, 25000, [(18800, 10), (20000, 20)]) == "リセットまで持つ見込み"
    assert gui.quota_forecast(50, 300, 25000, [(18800, 0), (20000, 50)]) == "約20分後に上限へ達する見込み"
    assert gui.quota_forecast(20, 300, 25000, [(18800, 20), (20000, 20)]) == "リセットまで持つ見込み"
    assert gui.quota_forecast(100, 300, 25000) == "利用上限に達しています"
    assert gui.quota_forecast(20, 300, 19000) == "リセット後のデータを待っています"
    assert gui.quota_forecast(20, 300, 25000, [(18800, 30), (20000, 20)]) == "履歴不足で予測できません"


def test_bad_remaining_numeric_value_is_not_parsed():
    assert gui.remaining_text("残り1..2% (使用20%)")[0] == ""


def test_shortcut_path_quote_is_escaped(tmp_path, monkeypatch):
    import subprocess
    captured = []
    monkeypatch.setattr(gui, "startup_dir", lambda: tmp_path / "don'tbreak")
    monkeypatch.setattr(gui, "autostart_target", lambda: ["C:/python.exe", "--tray"])
    import windows_shortcut
    monkeypatch.setattr(windows_shortcut, 'create', lambda *args: captured.append(args))
    assert gui.set_autostart(True)
    assert "don'tbreak" in str(captured[0][0])


def test_average_usage_per_hour_and_day(monkeypatch):
    monkeypatch.setattr("time.time", lambda: 2000000)
    assert gui.average_usage_text(30, 300, 2003600, [(1996400, 10), (2000000, 30)]) == "平均使用率：20.0% / 時間"
    assert gui.average_usage_text(40, 10080, 2086400, [(1913600, 20), (2000000, 40)]) == "平均使用率：20.0% / 日"

def test_average_usage_ignores_pre_reset_history(monkeypatch):
    monkeypatch.setattr("time.time", lambda: 2000000)
    assert gui.average_usage_text(15, 300, 2003600, [(1992800, 90), (1996400, 5), (2000000, 15)]) == "平均使用率：10.0% / 時間"
    assert gui.average_usage_text(15, 300, 2003600, [(2000000, 15)]) == "平均使用率：履歴不足"
    assert gui.average_usage_text(15, 300, 1999999, [(1996400, 5), (2000000, 15)]) == "平均使用率：リセット後の取得待ち"

def test_average_usage_flat_and_invalid(monkeypatch):
    monkeypatch.setattr("time.time", lambda: 2000000)
    assert gui.average_usage_text(15, 300, 2003600, [(1996400, 15), (2000000, 15)]) == "平均使用率：0.0% / 時間"
    assert gui.average_usage_text(float("nan"), 300, 2003600, []) == "平均使用率：データ不足"


def test_average_usage_visible_for_both_providers_and_survives_tick(app, monkeypatch, fake_home):
    from datetime import datetime, timezone

    now = 2000000
    monkeypatch.setattr("time.time", lambda: now)
    monkeypatch.setattr(gui.h, "recent", lambda metric, **kwargs: [(now - 3600, 10), (now, 30)])
    monkeypatch.setattr(app, "refresh", lambda: None)
    monkeypatch.setattr(app, "_schedule_tick", lambda: None)
    reset = now + 3600
    iso = datetime.fromtimestamp(reset, timezone.utc).isoformat()
    codex = gui.m.scan_codex(fake_home)
    codex.update({"has_rate": True, "rate_limits": {
        "primary": {"used_percent": 30, "resets_at": reset},
        "secondary": {"used_percent": 30, "resets_at": reset}}})
    claude = gui.m.scan_claude(fake_home)
    claude.update({"oauth": {"status": "ok", "five_hour": {"utilization": 30, "resets_at": iso},
                         "seven_day": {"utilization": 30, "resets_at": iso}}})
    app._render(codex, claude)
    app.update_idletasks()
    for label in (app.lbl5, app.cl_lbl5):
        assert "平均使用率：20.0% / 時間" in label.detail.cget("text")
    for label in (app.lblW, app.cl_lblW):
        assert "平均使用率：480.0% / 日" in label.detail.cget("text")
    app._tick()
    for label in (app.lbl5, app.cl_lbl5, app.lblW, app.cl_lblW):
        assert "平均使用率：" in label.detail.cget("text")

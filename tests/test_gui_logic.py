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

    def fake_run(args, **kwargs):
        captured["args"] = args
        return None

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert gui.set_autostart(True) is True
    ps = captured["args"][-1]
    assert r"C:\repo\gui.py" in ps
    assert "--tray" in ps


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
    monkeypatch.setattr(subprocess, "run", lambda args, **kwargs: captured.append(args))
    assert gui.set_autostart(True)
    assert "don''tbreak" in captured[0][-1]

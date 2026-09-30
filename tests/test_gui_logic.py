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

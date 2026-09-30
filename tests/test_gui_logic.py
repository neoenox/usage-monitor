"""GUI helpers that do not require a real desktop session."""
from __future__ import annotations

import gui


def test_autostart_arguments_keep_script_and_tray_flag():
    args = gui.autostart_arguments([
        r"C:\Python311\python.exe",
        r"C:\repo with spaces\gui.py",
        "--tray",
    ])
    assert "gui.py" in args
    assert "--tray" in args
    assert '"C:\\repo with spaces\\gui.py"' in args


def test_schedule_tick_replaces_existing_callback():
    calls: list[tuple[str, object]] = []

    class Dummy:
        _tick_after_id = "old"

        def after_cancel(self, callback_id):
            calls.append(("cancel", callback_id))

        def after(self, delay_ms, callback):
            calls.append(("after", delay_ms))
            return "new"

        def _tick(self):
            raise AssertionError("callback should not run during scheduling")

    app = Dummy()
    gui.App._schedule_tick(app)
    assert calls == [("cancel", "old"), ("after", 60_000)]
    assert app._tick_after_id == "new"

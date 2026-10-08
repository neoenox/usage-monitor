import gui
import monitor as m


def test_cli_gui_use_identical_forecast(monkeypatch):
    now = 2_000_000_000
    monkeypatch.setattr('time.time', lambda: now)
    for used, hist in ((90, []), (90, [(now-1200, 60), (now-600, 75)]),
                       (10, [(now-1200, 10), (now-600, 10)])):
        assert m.pace_label(used, 300, now+3600, hist) == gui.quota_forecast(used, 300, now+3600, hist)

import time

import gui


def test_unlinked_codex_is_not_written_as_zero_history():
    metrics, resets = gui.history_snapshot(
        {"has_rate": False},
        0.0,
        0.0,
        cl5=25.0,
        clw=None,
        pri={"resets_at": 111},
        sec={"resets_at": 222},
    )

    assert "codex_5h" not in metrics
    assert "codex_wk" not in metrics
    assert metrics == {"claude_5h": 25.0}
    assert resets == {}


def test_current_usage_breaks_bogus_flat_zero_history(monkeypatch):
    now = 10_000.0
    monkeypatch.setattr(time, "time", lambda: now)

    result = gui.quota_forecast(
        60.0,
        300,
        now + 3_600,
        hist=[(now - 1_200, 0.0), (now - 600, 0.0)],
        show_date=False,
    )

    assert result != "リセットまで持つ見込み"
    assert "上限へ達する見込み" in result


def test_forecast_remaining_quota_starts_from_now(monkeypatch):
    now = 20_000.0
    monkeypatch.setattr(time, "time", lambda: now)

    result = gui.quota_forecast(
        50.0,
        300,
        now + 7_200,
        hist=[(now - 1_200, 20.0), (now - 600, 40.0)],
        show_date=False,
    )

    assert "予測時刻を経過" not in result
    assert "上限へ達する見込み" in result

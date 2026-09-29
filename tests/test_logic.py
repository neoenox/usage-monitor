"""history.py / gui純粋ロジックのテスト。"""
from __future__ import annotations

import gui
import history as h


def test_history_record_recent(tmp_path):
    p = tmp_path / "h.db"
    h.record({"codex_5h": 73.0}, {"codex_5h": 123}, path=p)
    rows = h.recent("codex_5h", path=p)
    assert len(rows) == 1 and rows[0][1] == 73.0


def test_history_prune(tmp_path):
    import time

    p = tmp_path / "h.db"
    h.record({"codex_5h": 1.0}, path=p, ts=int(time.time()) - 31 * 86400)
    h.record({"codex_5h": 2.0}, path=p)
    rows = h.recent("codex_5h", path=p)
    assert [r[1] for r in rows] == [2.0]


def test_alert_levels():
    T = gui.TrayController
    assert T.alert_for(5, None) == "crit"
    assert T.alert_for(5, "crit") is None
    assert T.alert_for(15, None) == "warn"
    assert T.alert_for(15, "warn") is None
    assert T.alert_for(9, "warn") == "crit"
    assert T.alert_for(30, "warn") is None
    assert T.alert_for(20, None) == "warn"
    assert T.alert_for(10, None) == "crit"


def test_tray_tooltip(codex_data, claude_data):
    tip = gui.tray_tooltip(codex_data, claude_data)
    assert "Codex" in tip and "Claude" in tip

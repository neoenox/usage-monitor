"""E2E/単体テスト共通fixture: 疑似HOME (codex sessions + claude projects)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import monitor as m  # noqa: E402


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    """GUIテスト共有の単一Tkルート (複数ルートはWindowsで不安定なため)。
    Tkを作れない環境(CI等)ではスキップ。"""
    import tempfile

    import gui
    import history as h

    tmp = Path(tempfile.mkdtemp(prefix="usage-mon-test-"))
    orig_db = h.db_path
    orig_refresh = gui.App.refresh
    h.db_path = lambda: tmp / "hist.db"  # noqa: E731
    gui.App.refresh = lambda self: None  # noqa: E731
    try:
        a = gui.App()
    except Exception:
        h.db_path = orig_db
        gui.App.refresh = orig_refresh
        pytest.skip("tk unavailable on this runner")
    a.withdraw()
    yield a
    try:
        a.destroy()
    except Exception:
        pass
    h.db_path = orig_db
    gui.App.refresh = orig_refresh


def _codex_event(ts: str, used_p: float, used_s: float, inp: int, out: int,
                 resets_p: int = 1790654471, resets_s: int = 1791070697) -> str:
    return json.dumps({
        "timestamp": ts,
        "type": "event_msg",
        "payload": {
            "type": "token_count",
            "info": {"total_token_usage": {"input_tokens": inp, "output_tokens": out,
                                           "cached_input_tokens": inp // 2}},
            "rate_limits": {
                "limit_id": "codex", "plan_type": "plus",
                "primary": {"used_percent": used_p, "window_minutes": 300, "resets_at": resets_p},
                "secondary": {"used_percent": used_s, "window_minutes": 10080, "resets_at": resets_s},
            },
        },
    })


@pytest.fixture()
def fake_home(tmp_path: Path) -> Path:
    sess = tmp_path / ".codex" / "sessions" / "2026" / "09" / "29"
    sess.mkdir(parents=True)
    (sess / "rollout-a.jsonl").write_text(
        _codex_event("2026-09-29T01:00:00.000Z", 10.0, 20.0, 1000, 100) + "\n"
        + _codex_event("2026-09-29T02:00:00.000Z", 30.0, 20.0, 3000, 300) + "\n",
        encoding="utf-8",
    )
    (sess / "rollout-b.jsonl").write_text(
        _codex_event("2026-09-29T03:00:00.000Z", 50.0, 40.0, 5000, 500) + "\n",
        encoding="utf-8",
    )
    proj = tmp_path / ".claude" / "projects" / "P"
    proj.mkdir(parents=True)
    (proj / "s.jsonl").write_text(
        json.dumps({"message": {"usage": {"input_tokens": 10, "output_tokens": 20,
                                          "cache_creation_input_tokens": 1,
                                          "cache_read_input_tokens": 2}}}) + "\n",
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture()
def codex_data(fake_home: Path) -> dict:
    return m.scan_codex(fake_home)


@pytest.fixture()
def claude_data(fake_home: Path) -> dict:
    return m.scan_claude(fake_home)

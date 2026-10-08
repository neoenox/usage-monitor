"""SQLite concurrency and WAL locking regression tests."""
from concurrent.futures import ThreadPoolExecutor
import sqlite3
import time

import history


def test_wal_and_concurrent_gui_cli_recording(tmp_path):
    path = tmp_path / "history.db"
    history.init(path)
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    now = int(time.time())
    def writer(index):
        history.record({"codex_5h": float(index)}, path=path, ts=now + index)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(writer, range(40)))
    values = history.recent("codex_5h", path=path, limit=100)
    assert len(values) == 40
    assert sorted(v for _, v in values) == list(map(float, range(40)))

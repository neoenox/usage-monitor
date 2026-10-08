#!/usr/bin/env python3
"""履歴DB: スナップショットをSQLiteに記録し推移を取得 (stdlib only)."""
from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path


def db_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
    d = base / "usage-monitor"
    d.mkdir(parents=True, exist_ok=True)
    return d / "history.db"


def init(path: Path | None = None) -> Path:
    p = path or db_path()
    con = sqlite3.connect(p, timeout=10)
    try:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA busy_timeout=10000")
        con.execute(
            "CREATE TABLE IF NOT EXISTS snapshots("
            "ts INTEGER, metric TEXT, used REAL, resets_at INTEGER)"
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_snap ON snapshots(ts, metric)")
        con.commit()
    finally:
        con.close()
    return p


def record(metrics: dict[str, float], resets: dict[str, int | None] | None = None,
           path: Path | None = None, ts: int | None = None) -> None:
    p = init(path)
    now = int(ts or time.time())
    resets = resets or {}
    con = sqlite3.connect(p, timeout=10)
    try:
        con.executemany(
            "INSERT INTO snapshots(ts, metric, used, resets_at) VALUES(?,?,?,?)",
            [(now, k, float(v), resets.get(k)) for k, v in metrics.items()],
        )
        con.execute("DELETE FROM snapshots WHERE ts < ?", (now - 30 * 86400,))
        con.commit()
    finally:
        con.close()


def recent(metric: str, hours: int = 168, path: Path | None = None,
           limit: int = 500) -> list[tuple[int, float]]:
    p = path or db_path()
    if not p.exists():
        return []
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=10)
    try:
        rows = con.execute(
            "SELECT ts, used FROM snapshots WHERE metric=? AND ts>? "
            "ORDER BY ts DESC LIMIT ?",
            (metric, int(time.time()) - hours * 3600, limit),
        ).fetchall()
    finally:
        con.close()
    return sorted(rows)

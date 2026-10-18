"""E2E/単体テスト共通fixture: 疑似HOME (codex sessions + claude projects)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import monitor as m  # noqa: E402


# --- 実プロセス起動の共通ヘルパー -------------------------------------------
# E2Eは本物のプロセスを起動する。落ちたときの理由がトレースバックだけでは
# 分からない (素の subprocess.TimeoutExpired、windowedビルドの空stderr) ため、
# 起動は run_process() を通す: コマンド・timeout・実際の所要時間・終了コード・
# 両ストリームの末尾を失敗メッセージに残す。

DEFAULT_PROCESS_TIMEOUT = 120.0
_STREAM_TAIL = 2000


def _process_timeout() -> float:
    """既定のtimeout。遅いランナー向けに USAGE_MONITOR_TEST_TIMEOUT で上書きできる。"""
    raw = os.environ.get("USAGE_MONITOR_TEST_TIMEOUT", "").strip()
    if raw:
        try:
            value = float(raw)
        except ValueError:
            return DEFAULT_PROCESS_TIMEOUT
        if value > 0:
            return value
    return DEFAULT_PROCESS_TIMEOUT


def _tail(text, limit: int = _STREAM_TAIL) -> str:
    text = text or ""
    if not text.strip():
        return "<empty>"
    if len(text) <= limit:
        return text
    return f"<... {len(text) - limit} earlier chars omitted ...>\n{text[-limit:]}"


def _report(cmd, cwd, timeout, elapsed, outcome, returncode, stdout, stderr) -> str:
    return "\n".join([
        outcome,
        f"command: {' '.join(cmd)}",
        f"cwd: {cwd or Path.cwd()}",
        f"timeout: {timeout:g}s (USAGE_MONITOR_TEST_TIMEOUT overrides)",
        f"duration: {elapsed:.1f}s",
        f"returncode: {returncode}",
        f"--- stdout (tail) ---\n{_tail(stdout)}",
        f"--- stderr (tail) ---\n{_tail(stderr)}",
    ])


def run_process(cmd, *, timeout=None, env=None, cwd=None, input=None, expect=0):
    """テスト用 ``subprocess.run``: 出力を捕捉し、失敗時は理由を明示する。

    ``expect`` は要求する終了コード (既定 0)。失敗するはずの呼び出しでは
    ``expect=None`` を渡し、戻り値のプロセスに対して自分で assert する。
    """
    cmd = [str(part) for part in cmd]
    timeout = _process_timeout() if timeout is None else timeout
    started = time.monotonic()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace",
                              timeout=timeout, env=env, cwd=cwd, input=input)
    except subprocess.TimeoutExpired as exc:
        elapsed = time.monotonic() - started
        raise AssertionError(_report(
            cmd, cwd, timeout, elapsed,
            f"process timed out after {timeout:g}s (killed; partial output below)",
            getattr(exc, "returncode", None) or "killed",
            exc.stdout, exc.stderr)) from None
    elapsed = time.monotonic() - started
    if expect is not None:
        assert proc.returncode == expect, _report(
            cmd, cwd, timeout, elapsed,
            f"process exited {proc.returncode}, expected {expect}",
            proc.returncode, proc.stdout, proc.stderr)
    return proc


@pytest.fixture(name="run_process")
def _run_process_fixture():
    """``run_process`` ヘルパーをテストから使えるようにする (importに依存しない)。"""
    return run_process


@pytest.fixture(scope="session")
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
    except Exception as exc:
        import tkinter
        h.db_path = orig_db
        gui.App.refresh = orig_refresh
        if os.environ.get("GITHUB_ACTIONS") == "true" or not isinstance(exc, tkinter.TclError):
            raise
        pytest.skip(f"tk unavailable on this runner: {exc}")
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

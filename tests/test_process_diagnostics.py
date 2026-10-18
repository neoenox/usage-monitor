"""``run_process`` (tests/conftest.py) の診断契約テスト。

v0.6.4 の準備中、マージ直後の初回コールド実行で1件だけ失敗したが、素の
``subprocess`` 呼び出しでは「ハングしたのか・遅かっただけか・本当に落ちたのか」が
ログから読み取れず原因を特定できなかった。失敗メッセージが必ずその材料
(コマンド・timeout・所要時間・終了コード・両ストリームの末尾) を含むことを固定する。
"""
from __future__ import annotations

import sys

import pytest

SLEEP_FOREVER = "import time; print('starting', flush=True); time.sleep(30)"


def test_success_returns_the_completed_process(run_process):
    proc = run_process([sys.executable, "-c", "print('ok')"], timeout=60)
    assert proc.returncode == 0
    assert proc.stdout.strip() == "ok"


def test_nonzero_exit_reports_code_command_and_streams(run_process):
    script = "import sys; print('out'); sys.stderr.write('boom'); sys.exit(3)"
    with pytest.raises(AssertionError) as excinfo:
        run_process([sys.executable, "-c", script], timeout=60)

    message = str(excinfo.value)
    assert "process exited 3, expected 0" in message
    assert str(sys.executable) in message          # どのコマンドか
    assert "returncode: 3" in message              # 終了コード
    assert "duration:" in message                  # 遅かったのか即落ちたのか
    assert "out" in message and "boom" in message  # 両ストリーム
    assert "timed out" not in message              # 落ちた場合と区別できる


def test_timeout_reports_the_limit_and_keeps_partial_output(run_process):
    with pytest.raises(AssertionError) as excinfo:
        run_process([sys.executable, "-c", SLEEP_FOREVER], timeout=1.5)

    message = str(excinfo.value)
    assert "timed out after 1.5s" in message
    assert "starting" in message  # ハングまでの出力が残る


def test_expect_none_returns_the_failing_process(run_process):
    """失敗すると分かっている呼び出しはメッセージを出さず自分で assert する。"""
    proc = run_process([sys.executable, "-c", "import sys; sys.exit(4)"],
                       timeout=60, expect=None)
    assert proc.returncode == 4


def test_empty_streams_are_labelled(run_process):
    with pytest.raises(AssertionError) as excinfo:
        run_process([sys.executable, "-c", "pass"], timeout=60, expect=1)

    assert str(excinfo.value).count("<empty>") == 2


def test_long_output_is_truncated(run_process):
    script = "import sys; sys.stderr.write('x' * 5000); sys.exit(1)"
    with pytest.raises(AssertionError) as excinfo:
        run_process([sys.executable, "-c", script], timeout=60)

    message = str(excinfo.value)
    assert "earlier chars omitted" in message
    assert len(message) < 4000  # 全ログを失敗メッセージで埋めない


def test_env_override_sets_the_default_timeout(run_process, monkeypatch):
    monkeypatch.setenv("USAGE_MONITOR_TEST_TIMEOUT", "0.5")
    with pytest.raises(AssertionError) as excinfo:
        run_process([sys.executable, "-c", SLEEP_FOREVER])

    assert "timed out after 0.5s" in str(excinfo.value)


def test_invalid_env_override_falls_back_to_the_builtin_default(run_process, monkeypatch):
    monkeypatch.setenv("USAGE_MONITOR_TEST_TIMEOUT", "soon")
    proc = run_process([sys.executable, "-c", "import time; time.sleep(0.6)"])
    assert proc.returncode == 0  # 不正値で 0 秒や例外にならない


def test_explicit_timeout_beats_the_env_override(run_process, monkeypatch):
    monkeypatch.setenv("USAGE_MONITOR_TEST_TIMEOUT", "0.1")
    proc = run_process([sys.executable, "-c", "import time; time.sleep(0.4)"],
                       timeout=60)
    assert proc.returncode == 0

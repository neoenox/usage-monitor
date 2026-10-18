"""browser-extension の node テスト (``tests/*.test.cjs``) を全ゲートで実行する。

拡張機能のJSロジック (``background.js`` / ``parser.js``) には ``node:test`` の
テストが18件あったが、pytest からも CI からも実行されておらず、リリース
ワークフローは ``pytest`` しか回さないため、JSの回帰はそのまま公開され得た。
自然な呼び方 ``node --test tests/`` は node 22 で MODULE_NOT_FOUND になり、
失敗しているように見えるのも誤解を招く。

ファイル一覧をPython側で列挙して node に渡すのは、``--test`` の glob 解釈が
node のバージョンに依存するため。新しい ``*.test.cjs`` は自動で拾われる。
"""
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
NODE_TESTS = sorted((ROOT / "tests").glob("*.test.cjs"))
# node --test は非TTY (ここではパイプ) でTAPを出力する。
TESTS_LINE = re.compile(r"^# tests (\d+)$", re.M)


def test_extension_node_suite_runs_with_the_python_suite(run_process):
    if shutil.which("node") is None:
        if os.environ.get("GITHUB_ACTIONS") == "true":
            pytest.fail("node is required to gate the browser extension tests")
        pytest.skip("node is required")

    assert NODE_TESTS, "tests/*.test.cjs がない (拡張機能のテストが消えた?)"

    proc = run_process(["node", "--test", *[str(path) for path in NODE_TESTS]],
                       cwd=ROOT, timeout=180)

    summary = TESTS_LINE.search(proc.stdout)
    assert summary, f"node --test のTAPサマリを読めません:\n{proc.stdout[-2000:]}"
    counted = int(summary.group(1))
    assert counted >= len(NODE_TESTS), (
        f"{len(NODE_TESTS)}ファイル中{counted}件しか実行されていません:\n{proc.stdout[-2000:]}")
    assert "# fail 0" in proc.stdout, proc.stdout[-2000:]

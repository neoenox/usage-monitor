"""browser-extension の node テスト (``tests/*.test.cjs``) を全ゲートで実行する。

拡張機能のJSロジック (``background.js`` / ``parser.js`` / ``content.js``) には
``node:test`` のテストが30件あったが、pytest からも CI からも実行されておらず、
リリースワークフローは ``pytest`` しか回さないため、JSの回帰はそのまま公開され得た。
自然な呼び方 ``node --test tests/`` は node 22 で MODULE_NOT_FOUND になり、
失敗しているように見えるのも誤解を招く。

1ファイルずつ実行するのは、テストが1件も登録されないファイルを node が
「ファイル自身を名前とする1件の pass」として報告するため。まとめて実行して
合計件数だけを見ると、あるファイルのテストが黙って収集されなくなっても
他のファイルの件数に埋もれる。ファイルごとに「ファイル自身以外のサブテストが
1件以上ある」ことを要求すれば、そのファイル名で失敗する。

ファイル一覧をPython側で列挙するのは、``--test`` の glob 解釈が node の
バージョンに依存するため。新しい ``*.test.cjs`` は自動で拾われる。
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
SUBTEST_LINE = re.compile(r"^# Subtest: (.+)$", re.M)


def _require_node() -> None:
    if shutil.which("node") is None:
        if os.environ.get("GITHUB_ACTIONS") == "true":
            pytest.fail("node is required to gate the browser extension tests")
        pytest.skip("node is required")


def _registered_tests(stdout: str, path: Path) -> list[str]:
    """TAPのサブテスト名から、テスト0件のときの「ファイル自身」の報告を除く。"""
    names = [name.strip() for name in SUBTEST_LINE.findall(stdout)]
    return [name for name in names if Path(name) != path]


def test_extension_node_suite_has_files():
    """ファイルが1つも無いと parametrize が空になり、pytest は黙って skip する。"""
    assert NODE_TESTS, "tests/*.test.cjs がない (拡張機能のテストが消えた?)"


@pytest.mark.parametrize("path", NODE_TESTS, ids=lambda path: path.name)
def test_extension_node_file_runs_and_registers_its_tests(path, run_process):
    """ファイルごとに node --test を回し、そのファイル名で失敗するようにする。"""
    _require_node()

    proc = run_process(["node", "--test", str(path)], cwd=ROOT, timeout=180)

    summary = TESTS_LINE.search(proc.stdout)
    assert summary, f"{path.name}: node --test のTAPサマリを読めません:\n{proc.stdout[-2000:]}"
    assert int(summary.group(1)) >= 1, (
        f"{path.name}: テストが1件も実行されていません:\n{proc.stdout[-2000:]}")
    assert "# fail 0" in proc.stdout, proc.stdout[-2000:]

    # まとめて実行したときは見えない穴。テストが1件も登録されないファイルは
    # ファイル自身を名前とする1件の pass になるので、合計件数では気づけない。
    registered = _registered_tests(proc.stdout, path)
    assert registered, (
        f"{path.name}: 登録されたテストがありません (node はファイル自身を1件の pass と "
        f"して報告します):\n{proc.stdout[-2000:]}")


def test_registered_tests_ignores_the_file_level_fallback():
    """テスト0件のファイルの報告の形を、実測した内容で固定する。"""
    path = ROOT / "tests" / "example.test.cjs"
    empty = (
        "TAP version 13\n"
        f"# Subtest: {path}\n"
        f"ok 1 - {path}\n"
        "  ---\n  duration_ms: 55.9\n  type: 'test'\n  ...\n"
        "1..1\n# tests 1\n# pass 1\n# fail 0\n"
    )
    assert _registered_tests(empty, path) == []
    assert TESTS_LINE.search(empty).group(1) == "1"  # 件数だけでは0件と区別できない

    real = (
        "TAP version 13\n"
        "# Subtest: night rollover and same weekday next week\n"
        "ok 1 - night rollover and same weekday next week\n"
        "1..1\n# tests 1\n# pass 1\n# fail 0\n"
    )
    assert _registered_tests(real, path) == ["night rollover and same weekday next week"]

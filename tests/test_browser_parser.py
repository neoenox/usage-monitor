"""Bilingual usage-page parser checks (Japanese + English). Skips when node is missing."""
import shutil
import subprocess
from pathlib import Path

import pytest

PARSER = Path(__file__).resolve().parent.parent / "browser-extension" / "parser.js"


def run_node(script: str) -> str:
    proc = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


@pytest.mark.skipif(shutil.which("node") is None, reason="node is required")
def test_parser_accepts_japanese_and_english():
    script = (
        "const p=require(%r);"
        "const now=new Date('2026-10-12T10:00:00+09:00');"
        "const ja=p.parseRows(["
        "{label:'現在のセッション',used:15,resetText:'13:30にリセット'},"
        "{label:'今週',used:88,resetText:'月曜日に13:30にリセット'}],now);"
        "const en=p.parseRows(["
        "{label:'Current session',used:20,resetText:'Resets at 1:30 PM'},"
        "{label:'This week',used:70,resetText:'Resets Monday at 1:30 PM'}],now);"
        "console.log(JSON.stringify({ja:!!ja,en:!!en,"
        "ja5:ja && ja.rate_limits.five_hour.used_percentage,"
        "en7:en && en.rate_limits.seven_day.used_percentage}));"
    ) % str(PARSER)
    import json
    result = json.loads(run_node(script))
    assert result == {"ja": True, "en": True, "ja5": 15, "en7": 70}


@pytest.mark.skipif(shutil.which("node") is None, reason="node is required")
def test_parser_rejects_unknown_labels():
    script = (
        "const p=require(%r);"
        "const now=new Date('2026-10-12T10:00:00+09:00');"
        "const bad=p.parseRows(["
        "{label:'Something else',used:10,resetText:'Resets at 1:30 PM'},"
        "{label:'This week',used:70,resetText:'Resets Monday at 1:30 PM'}],now);"
        "console.log(JSON.stringify({bad}));"
    ) % str(PARSER)
    import json
    assert json.loads(run_node(script)) == {"bad": None}

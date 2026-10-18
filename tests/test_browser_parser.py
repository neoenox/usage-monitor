"""Bilingual usage-page parser checks (Japanese + English). Skips when node is missing.

Reset times are built relative to the runner clock because the parser
interprets them in the machine-local timezone (same as the real page).
"""
import shutil
from pathlib import Path

import pytest

PARSER = Path(__file__).resolve().parent.parent / "browser-extension" / "parser.js"

SCRIPT = """
const p = require(%r);
const now = new Date();
const t5 = new Date(now.getTime() + 2 * 3600 * 1000);
const pad = (n) => String(n).padStart(2, '0');
const h24 = `${t5.getHours()}:${pad(t5.getMinutes())}`;
const h12 = (t5.getHours() %% 12) || 12;
const ap = t5.getHours() < 12 ? 'AM' : 'PM';
const daysEn = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const daysJa = ['日', '月', '火', '水', '木', '金', '土'];
const ja = p.parseRows([
  {label: '現在のセッション', used: 15, resetText: `${h24}にリセット`},
  {label: '今週', used: 88, resetText: `${daysJa[t5.getDay()]}曜日に${h24}にリセット`}], now);
const en = p.parseRows([
  {label: 'Current session', used: 20, resetText: `Resets at ${h12}:${pad(t5.getMinutes())} ${ap}`},
  {label: 'This week', used: 70, resetText: `Resets ${daysEn[t5.getDay()]} at ${h12}:${pad(t5.getMinutes())} ${ap}`}], now);
console.log(JSON.stringify({ja: !!ja, en: !!en,
  ja5: ja && ja.rate_limits.five_hour.used_percentage,
  en7: en && en.rate_limits.seven_day.used_percentage}));
""" % str(PARSER)


def run_node(run_process, script: str) -> str:
    proc = run_process(["node", "-e", script], timeout=30)
    return proc.stdout.strip()


@pytest.mark.skipif(shutil.which("node") is None, reason="node is required")
def test_parser_accepts_japanese_and_english(run_process):
    import json
    result = json.loads(run_node(run_process, SCRIPT))
    assert result == {"ja": True, "en": True, "ja5": 15, "en7": 70}


@pytest.mark.skipif(shutil.which("node") is None, reason="node is required")
def test_parser_rejects_unknown_labels(run_process):
    script = (
        "const p=require(%r);"
        "const bad=p.parseRows(["
        "{label:'Something else',used:10,resetText:'Resets at 1:30 PM'},"
        "{label:'This week',used:70,resetText:'Resets Monday at 1:30 PM'}]);"
        "console.log(JSON.stringify({bad}));"
    ) % str(PARSER)
    import json
    assert json.loads(run_node(run_process, script)) == {"bad": None}

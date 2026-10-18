"""バージョンリソース生成と `--version` の入口テスト (#77)。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import monitor as m
import windows_version as wv

ROOT = Path(__file__).resolve().parent.parent


def test_resource_fields_follow_monitor_version():
    text = wv.build_version_resource()
    assert f"filevers={wv.version_tuple(m.__version__)}" in text
    assert f"prodvers={wv.version_tuple(m.__version__)}" in text
    assert f"StringStruct(u'FileVersion', u'{m.__version__}')" in text
    assert f"StringStruct(u'ProductVersion', u'{m.__version__}')" in text
    assert "StringStruct(u'OriginalFilename', u'usage-monitor.exe')" in text


def test_resource_filename_applies_to_browser_host():
    text = wv.build_version_resource(filename="usage-monitor-browser-host.exe")
    assert "StringStruct(u'OriginalFilename', u'usage-monitor-browser-host.exe')" in text
    assert "StringStruct(u'InternalName', u'usage-monitor-browser-host')" in text


def test_version_tuple_forms():
    assert wv.version_tuple("0.6.2") == (0, 6, 2, 0)
    assert wv.version_tuple("1.2.3.4") == (1, 2, 3, 4)
    assert wv.dotted("0.6.2") == "0.6.2.0"
    with pytest.raises(ValueError):
        wv.version_tuple("0.6")


def test_generator_writes_resource_file(tmp_path):
    out = tmp_path / "version-info.txt"
    assert wv.main(["--out", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert text.startswith("VSVersionInfo(")
    assert f"u'{m.__version__}'" in text


def test_gui_version_flag_exits_without_window():
    """`--version` はウィンドウを作らず即終了し、コンソールがあれば表示する。"""
    proc = subprocess.run([sys.executable, "gui.py", "--version"], cwd=ROOT,
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr[-300:]
    assert m.__version__ in proc.stdout

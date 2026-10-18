"""Opt-in smoke tests against the built browser-host / main executables (#37 / T5).

Runs only with ``TEST_PACKAGED_EXPORT=1`` after ``build.ps1``. Registry-writing
paths are exercised only for rejection, and ``LOCALAPPDATA`` is redirected to a
temporary directory so no user state is touched.
"""
import json
import os
import subprocess
from pathlib import Path

import pytest

import monitor
import windows_version

HOST = Path("dist/usage-monitor-browser-host.exe")
MAIN = Path("dist/usage-monitor.exe")

pytestmark = pytest.mark.skipif(
    os.environ.get("TEST_PACKAGED_EXPORT") != "1",
    reason="Opt-in packaged artifact integration")


def _run(args, tmp_path):
    env = dict(os.environ, LOCALAPPDATA=str(tmp_path))
    return subprocess.run([str(HOST.resolve()), *args], env=env, timeout=30,
                          capture_output=True, text=True, errors="replace")


def test_host_imports_numeric_payload_to_temp_appdata(tmp_path):
    payload = {"rate_limits": {
        "five_hour": {"used_percentage": 25, "resets_at": 2000000000},
        "seven_day": {"used_percentage": 40, "resets_at": 2000000000}}}
    source = tmp_path / "payload.json"
    source.write_text(json.dumps(payload), encoding="utf-8")

    proc = _run(["--import", str(source)], tmp_path)
    assert proc.returncode == 0, proc.stderr[-300:]

    saved = json.loads((tmp_path / "usage-monitor" / "claude-browser-quota.json").read_text(encoding="utf-8"))
    assert saved["windows"]["five_hour"]["utilization"] == 25
    assert saved["windows"]["seven_day"]["utilization"] == 40


def test_host_rejects_invalid_extension_id_without_writing(tmp_path):
    proc = _run(["--register", "not-a-valid-id"], tmp_path)
    assert proc.returncode != 0
    assert not (tmp_path / "usage-monitor" / "browser-native-host.json").exists()


def test_host_requires_extension_origin(tmp_path):
    proc = _run([], tmp_path)
    assert proc.returncode != 0
    assert "extension" in (proc.stdout + proc.stderr).lower()


def test_main_exe_embeds_brand_icon():
    assert MAIN.exists(), "build dist/usage-monitor.exe first"
    assert b"app.ico" in MAIN.read_bytes()


@pytest.mark.skipif(os.name != "nt", reason="Windows version resource")
def test_main_exe_exposes_version_resource():
    assert MAIN.exists(), "build dist/usage-monitor.exe first"
    assert windows_version.read_file_version(MAIN) == windows_version.dotted(monitor.__version__)

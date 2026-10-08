"""Opt-in test against an existing built Windows executable."""
import json
import os
from pathlib import Path
import subprocess
import pytest


@pytest.mark.skipif(os.environ.get('TEST_PACKAGED_EXPORT') != '1', reason='Opt-in packaged artifact integration')
def test_windowed_exe_exports_piped_json(tmp_path):
    executable = Path('dist/usage-monitor.exe').resolve()
    env = dict(os.environ, LOCALAPPDATA=str(tmp_path))
    payload = {'secret': 'NEVER', 'rate_limits': {'five_hour': {'used_percentage': 25, 'resets_at': 2000000000}}}
    result = subprocess.run([str(executable), '--claude-export'], input=json.dumps(payload).encode(), env=env, timeout=30, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    assert result.returncode == 0
    target = tmp_path/'usage-monitor'/'claude-quota.json'
    saved = target.read_text()
    assert 'NEVER' not in saved
    assert json.loads(saved)['windows']['five_hour']['utilization'] == 25

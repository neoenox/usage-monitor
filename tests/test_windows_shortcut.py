import json
import subprocess
import sys
import pytest
import gui


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows COM shortcut')
def test_real_shortcut_with_spaces_apostrophes_and_unicode(tmp_path, monkeypatch):
    folder = tmp_path / "日本語 O'Brien space"
    folder.mkdir()
    monkeypatch.setattr(gui, 'startup_dir', lambda: folder)
    executable = str(folder/'monitor app.exe')
    monkeypatch.setattr(gui, 'autostart_target', lambda: [executable, '--tray'])
    original_run = subprocess.run
    def diagnostic_run(*args, **kwargs):
        try:
            return original_run(*args, **kwargs)
        except subprocess.CalledProcessError as exc:
            pytest.fail(f'PowerShell failed: {exc.returncode}; stderr={exc.stderr!r}')
    monkeypatch.setattr(subprocess, 'run', diagnostic_run)
    assert gui.set_autostart(True)
    shortcut = str(folder/gui.STARTUP_LNK).replace("'", "''")
    command = f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{shortcut}'); @{{target=$s.TargetPath;args=$s.Arguments;working=$s.WorkingDirectory}} | ConvertTo-Json -Compress"
    import base64
    command = '[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding; ' + command
    encoded = base64.b64encode(command.encode('utf-16le')).decode('ascii')
    result = subprocess.run(['powershell', '-NoProfile', '-EncodedCommand', encoded], capture_output=True, check=True)
    data = json.loads(result.stdout.decode('utf-8-sig'))
    assert data['target'].lower() == executable.lower()
    assert data['args'] == '--tray'
    assert data['working'].lower() == str(folder).lower()
    assert gui.set_autostart(False)
    assert not (folder/gui.STARTUP_LNK).exists()

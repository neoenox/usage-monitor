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
    assert gui.set_autostart(True)
    shortcut = str(folder/gui.STARTUP_LNK).replace("'", "''")
    command = f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{shortcut}'); @{{target=$s.TargetPath;args=$s.Arguments;working=$s.WorkingDirectory}} | ConvertTo-Json -Compress"
    result = subprocess.run(['powershell', '-NoProfile', '-Command', command], capture_output=True, check=True)
    data = json.loads(result.stdout.decode('utf-8-sig'))
    assert data['target'].lower() == executable.lower()
    assert data['args'] == '--tray'
    assert data['working'].lower() == str(folder).lower()
    assert gui.set_autostart(False)
    assert not (folder/gui.STARTUP_LNK).exists()

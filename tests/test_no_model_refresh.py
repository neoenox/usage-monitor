import subprocess
import monitor as m


def test_auth_recovery_never_invokes_model(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr('shutil.which', lambda _: 'claude.exe')
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: calls.append(a))
    m._cli_refresh_creds(tmp_path)
    assert calls == []

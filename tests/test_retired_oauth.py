import monitor as m


def test_rollback_keeps_isolated_home_and_never_invokes_model(tmp_path, monkeypatch):
    monkeypatch.setenv('CLAUDE_CODE_OAUTH_TOKEN', 'must-not-use')
    monkeypatch.setattr(m, 'claude_token_from_os_store', lambda: (_ for _ in ()).throw(AssertionError('host credentials')))
    assert m.claude_token(tmp_path, isolated=True) == ''
    assert m.claude_has_creds(tmp_path, isolated=True) is False
    assert m.fetch_claude_oauth(tmp_path, isolated=True)['status'] == 'unsupported'
    assert m._cli_refresh_creds(tmp_path) is False


def test_statusline_export_only_reports_ok_or_missing(tmp_path):
    """The credential-free export can never surface an auth-expiry state."""
    import json

    import claude_export

    target = tmp_path / "quota.json"
    payloads = [None, "garbage", {}, {"windows": {}}, {"observed_at": 1},
                {"observed_at": "x"}, {"observed_at": 1, "windows": {"five_hour": {}}}]
    for payload in payloads:
        if payload is None:
            target.unlink(missing_ok=True)
        else:
            target.write_text(json.dumps(payload), encoding="utf-8")
        assert claude_export.read(target)["status"] in {"ok", "missing_token"}


def test_no_expired_or_auto_refresh_guidance_in_code():
    import inspect

    for module in (m,):
        src = inspect.getsource(module)
        assert "auto-refresh failed" not in src
        assert '"expired"' not in src

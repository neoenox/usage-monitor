import monitor as m


def test_rollback_keeps_isolated_home_and_never_invokes_model(tmp_path, monkeypatch):
    monkeypatch.setenv('CLAUDE_CODE_OAUTH_TOKEN', 'must-not-use')
    monkeypatch.setattr(m, 'claude_token_from_os_store', lambda: (_ for _ in ()).throw(AssertionError('host credentials')))
    assert m.claude_token(tmp_path, isolated=True) == ''
    assert m.claude_has_creds(tmp_path, isolated=True) is False
    assert m.fetch_claude_oauth(tmp_path, isolated=True)['status'] == 'missing_token'
    assert m._cli_refresh_creds(tmp_path) is False

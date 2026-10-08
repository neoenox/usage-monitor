import monitor as m


def test_retired_auth_interfaces_never_read_or_refresh(tmp_path, monkeypatch):
    monkeypatch.setenv('CLAUDE_CODE_OAUTH_TOKEN', 'must-not-use')
    assert m.claude_token(tmp_path) == ''
    assert m.claude_has_creds(tmp_path) is False
    assert m._resolve_oauth_access({'accessToken': 'secret'}) == ''
    assert m._refresh_oauth('secret') == ''
    assert m.claude_token_from_os_store() == ''
    assert m._read_credential_store('anything') == ''
    assert m.fetch_claude_oauth(tmp_path)['status'] == 'unsupported'

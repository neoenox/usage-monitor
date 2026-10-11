"""The monitor must not independently refresh Claude authentication."""
import monitor as m


def test_retired_refresh_never_uses_network_or_credentials(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('credential or network access')
    monkeypatch.setattr(m.urllib.request, 'urlopen', forbidden)
    monkeypatch.setattr(m, '_read_credential_store', forbidden)
    monkeypatch.setenv('CLAUDE_CODE_OAUTH_TOKEN', 'must-not-read')
    assert m.claude_token(tmp_path) == ''
    assert m.claude_has_creds(tmp_path) is False
    assert m._resolve_oauth_access({'accessToken': 'old', 'refreshToken': 'r'}) == ''
    assert m._refresh_oauth('r') == ''
    assert m.fetch_claude_oauth(tmp_path)['status'] == 'unsupported'

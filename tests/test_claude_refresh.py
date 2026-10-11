import json
import time
import urllib.error

import monitor as m


class Response:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self):
        return json.dumps({'access_token': 'new-access', 'refresh_token': 'new-refresh',
                           'expires_in': 28800}).encode()


def test_refresh_saved_and_reused_after_restart(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local'))
    creds = tmp_path / '.claude' / '.credentials.json'
    creds.parent.mkdir()
    creds.write_text(json.dumps({'other': {'keep': True}, 'claudeAiOauth': {
        'accessToken': 'old', 'refreshToken': 'old-refresh', 'expiresAt': 1,
        'subscriptionType': 'max'}}))
    calls = []

    def request(req, **kwargs):
        calls.append(req.full_url)
        assert json.loads(req.data)['refresh_token'] == 'old-refresh'
        return Response()

    monkeypatch.setattr(m.urllib.request, 'urlopen', request)
    assert m.claude_token(tmp_path, isolated=True) == 'new-access'
    saved = json.loads(creds.read_text())
    assert saved['other'] == {'keep': True}
    assert saved['claudeAiOauth']['refreshToken'] == 'new-refresh'
    assert saved['claudeAiOauth']['expiresAt'] > time.time() * 1000
    assert saved['claudeAiOauth']['subscriptionType'] == 'max'
    assert m.claude_token(tmp_path, isolated=True) == 'new-access'
    assert calls == ['https://platform.claude.com/v1/oauth/token']


def test_refresh_429_does_not_change_credentials_or_repeat(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local'))
    creds = tmp_path / '.claude' / '.credentials.json'
    creds.parent.mkdir()
    original = json.dumps({'claudeAiOauth': {'accessToken': 'old', 'refreshToken': 'r', 'expiresAt': 1}})
    creds.write_text(original)
    calls = []

    def request(req, **kwargs):
        calls.append(req.full_url)
        raise urllib.error.HTTPError(req.full_url, 429, 'limited', {}, None)

    monkeypatch.setattr(m.urllib.request, 'urlopen', request)
    for _ in range(2):
        assert m.fetch_claude_oauth(tmp_path, isolated=True)['detail'] == 'rate_limited_retry_later'
    assert len(calls) == 1
    assert creds.read_text() == original


def test_refresh_does_not_overwrite_newer_official_login(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local'))
    creds = tmp_path / '.claude' / '.credentials.json'
    creds.parent.mkdir()
    creds.write_text(json.dumps({'claudeAiOauth': {'accessToken': 'old', 'refreshToken': 'r', 'expiresAt': 1}}))
    newer = {'claudeAiOauth': {'accessToken': 'official-new', 'refreshToken': 'official-refresh',
                              'expiresAt': int(time.time() * 1000) + 28800000}}

    def request(req, **kwargs):
        creds.write_text(json.dumps(newer))
        return Response()

    monkeypatch.setattr(m.urllib.request, 'urlopen', request)
    assert m.claude_token(tmp_path, isolated=True) == 'official-new'
    assert json.loads(creds.read_text()) == newer


def test_invalid_expiry_does_not_write_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local'))
    path = tmp_path / 'credentials.json'
    original = json.dumps({'claudeAiOauth': {'accessToken': 'old', 'refreshToken': 'r', 'expiresAt': 1}})
    path.write_text(original)
    monkeypatch.setattr(Response, 'read', lambda self: b'{"access_token":"new","expires_in":false}')
    monkeypatch.setattr(m.urllib.request, 'urlopen', lambda *a, **kw: Response())
    assert m._refresh_oauth('r', credential_path=path) == ''
    assert path.read_text() == original
    assert not list(tmp_path.glob('.credentials-monitor-*'))


def test_cached_error_reason_is_visible(tmp_path):
    import gui
    import usage_cache

    path = tmp_path / 'cache.json'
    good = {'oauth': {'status': 'ok', 'five_hour': {'utilization': 1}, 'seven_day': {'utilization': 2}}}
    usage_cache.apply({}, good, path)
    _, cached = usage_cache.apply({}, {'oauth': {'status': 'expired', 'detail': 'rate_limited_retry_later'}}, path)
    assert cached['fetch_detail'] == 'rate_limited_retry_later'
    _, explanation = gui.setup_guidance({}, cached)
    assert '429' in explanation
    assert '再ログインせず' in explanation


def test_old_endpoint_backoff_does_not_block_corrected_endpoint(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    p = m._refresh_backoff_path()
    p.parent.mkdir()
    p.write_text(json.dumps({'failed_at': time.time(), 'cooldown': 3600, 'rate_limited': True}))
    assert not m._refresh_backoff_active()
    m._record_refresh_failure(True)
    assert m._refresh_backoff_active()


def test_concurrent_monitor_does_not_refresh_same_token(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local'))
    path = tmp_path / 'credentials.json'
    path.write_text(json.dumps({'claudeAiOauth': {'accessToken': 'old', 'refreshToken': 'r', 'expiresAt': 1}}))
    calls = []

    def request(req, **kwargs):
        calls.append(req.full_url)
        assert m._refresh_oauth('r', credential_path=path) == ''
        return Response()

    monkeypatch.setattr(m.urllib.request, 'urlopen', request)
    assert m._refresh_oauth('r', credential_path=path) == 'new-access'
    assert len(calls) == 1

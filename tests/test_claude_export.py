import json
import pytest
import claude_export as c


def test_interleaved_exports_have_independent_staging(tmp_path, monkeypatch):
    from pathlib import Path
    target = tmp_path/'quota.json'
    replace = Path.replace
    staged = []
    def interleave(source, destination):
        if destination == target:
            staged.append(source)
            if len(staged) == 1:
                c.export({}, target, now=1900000001)
        return replace(source, destination)
    monkeypatch.setattr(Path, 'replace', interleave)
    c.export({}, target, now=1900000000)
    assert len(set(staged)) == 2
    assert json.loads(target.read_text())['observed_at'] == 1900000000
    assert list(tmp_path.iterdir()) == [target]


def test_scan_uses_export_without_auth_access(tmp_path, monkeypatch):
    import monitor as m
    target = c.path(tmp_path)
    c.export({'rate_limits': {'five_hour': {'used_percentage': 25, 'resets_at': 2000000000}}}, target, now=1900000000)
    def forbidden(*args, **kwargs):
        raise AssertionError('credential or network access')
    monkeypatch.setattr(m, 'fetch_claude_oauth', forbidden)
    out = m.scan_claude(tmp_path)
    assert out['oauth']['five_hour']['utilization'] == 25
    assert out['observed_at'] == 1900000000
    assert out['quota_cached'] is True
    assert out['quota_source'] == 'statusline'


def test_partial_export_renders_and_ticks(app, tmp_path):
    import monitor as m
    import usage_cache
    c.export({'rate_limits': {'five_hour': {'used_percentage': 25, 'resets_at': 2000000000}}}, c.path(tmp_path), now=1900000000)
    codex = m.scan_codex(tmp_path)
    claude = {'files': 0, 'messages': 0, 'input': 0, 'output': 0, 'total': 0, 'oauth': c.read(c.path(tmp_path)), 'observed_at': 1900000000, 'quota_cached': True, 'quota_source': 'statusline'}
    codex, claude = usage_cache.apply(codex, claude, tmp_path/'cache.json', now=1950000000)
    assert claude['observed_at'] == 1900000000
    app._render(codex, claude)
    app._last = codex, claude
    app._tick()
    assert '残り75%' in app.cl_lbl5.cget('text')
    assert 'Claude Code利用時' in app.cl_lbl5.cget('text')
    assert '更新失敗' not in app.cl_lbl5.cget('text')


def test_export_only_numeric_quota(tmp_path):
    target = tmp_path/'quota.json'
    c.export({'secret': 'NEVER', 'rate_limits': {'five_hour': {'used_percentage': 25, 'resets_at': 2000000000}}}, target, now=1900000000)
    saved = target.read_text()
    assert 'NEVER' not in saved
    assert c.read(target)['five_hour']['utilization'] == 25
    assert c.read(target)['observed_at'] == 1900000000


@pytest.mark.parametrize('value', [True, -1, 101, float('nan'), 'secret'])
def test_invalid_usage_rejected(tmp_path, value):
    target = tmp_path/'quota.json'
    c.export({'rate_limits': {'five_hour': {'used_percentage': value, 'resets_at': 2000000000}}}, target)
    assert c.read(target)['status'] == 'missing_token'


def test_missing_window_removes_previous_data(tmp_path):
    target = tmp_path/'quota.json'
    c.export({'rate_limits': {'five_hour': {'used_percentage': 25, 'resets_at': 2000000000}}}, target)
    c.export({}, target)
    assert c.read(target)['status'] == 'missing_token'


def test_missing_statusline_does_not_show_old_direct_cache(tmp_path):
    import monitor as m
    import usage_cache
    cache = tmp_path / 'cache.json'
    usage_cache.apply({}, {'oauth': {'status': 'ok', 'five_hour': {'utilization': 94},
                                    'seven_day': {'utilization': 86}}}, cache)
    _, result = usage_cache.apply({}, m.scan_claude(tmp_path), cache)
    assert result['oauth']['status'] == 'missing_token'
    assert not result['quota_cached']


def test_statusline_preserves_pacing_and_records_observation_once(app, tmp_path, monkeypatch):
    import gui
    import monitor as m
    import history as h
    now = 2000000
    monkeypatch.setattr('time.time', lambda: now)
    monkeypatch.setattr(app, '_schedule_tick', lambda: None)
    h.record({'claude_5h': 10}, ts=now - 3600)
    c.export({'rate_limits': {'five_hour': {'used_percentage': 30, 'resets_at': now + 3600}}},
             c.path(tmp_path), now=now)
    codex, claude = m.scan_codex(tmp_path), m.scan_claude(tmp_path)
    app._render(codex, claude)
    app._render(codex, claude)
    assert sum(t == now for t, u in h.recent('claude_5h')) == 1
    text = app.cl_lbl5.cget('text')
    assert '平均使用率：20.0% / 時間' in text
    assert '\n観測時の利用目安：70.0% / 時間まで' in text
    assert '観測値' in text
    app._tick()
    assert app.cl_lbl5.cget('text') == text

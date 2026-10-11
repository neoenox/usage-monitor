import io
import json
import struct

import pytest


def payload():
    return {'rate_limits': {
        'five_hour': {'used_percentage': 13, 'resets_at': 2000003600},
        'seven_day': {'used_percentage': 88, 'resets_at': 2000172800}}}


def test_browser_observation_reaches_scanner_and_gui(app, tmp_path):
    import claude_browser as browser
    import monitor
    import usage_cache
    browser.import_usage(payload(), browser.path(tmp_path), now=2000000000)
    claude = monitor.scan_claude(tmp_path)
    assert claude['quota_source'] == 'browser'
    assert claude['oauth']['five_hour']['utilization'] == 13
    codex, claude = usage_cache.apply(monitor.scan_codex(tmp_path), claude, tmp_path/'cache.json', now=2000000100)
    assert claude['observed_at'] == 2000000000
    app._render(codex, claude)
    assert '残り87%' in app.cl_lbl5.cget('text')
    assert '残り12%' in app.cl_lblW.cget('text')
    assert 'ブラウザ' in app.cl_lbl5.cget('text')
    assert '更新失敗' not in app.cl_lbl5.cget('text')


def test_native_protocol_filters_extras_and_preserves_last_good_on_failure(tmp_path):
    import claude_browser as browser
    target = tmp_path/'quota.json'
    sample = payload() | {'secret': 'NEVER-SAVE'}
    raw = json.dumps(sample).encode()
    output = io.BytesIO()
    browser.serve(io.BytesIO(struct.pack('<I', len(raw))+raw), output, target)
    reply = output.getvalue()
    assert json.loads(reply[4:])['ok']
    assert 'NEVER-SAVE' not in target.read_text()
    previous = target.read_bytes()
    with pytest.raises(ValueError):
        browser.import_usage({'rate_limits': {}}, target)
    assert target.read_bytes() == previous


@pytest.mark.parametrize('value', [True, -1, 101, float('nan'), '13'])
def test_invalid_browser_usage_rejected(tmp_path, value):
    import claude_browser as browser
    sample = payload()
    sample['rate_limits']['five_hour']['used_percentage'] = value
    with pytest.raises(ValueError):
        browser.import_usage(sample, tmp_path/'quota.json')
    assert not (tmp_path/'quota.json').exists()


def test_latest_observation_wins(tmp_path):
    import claude_browser as browser
    import claude_export
    import monitor
    browser.import_usage(payload(), browser.path(tmp_path), now=2000000000)
    claude_export.export(payload(), claude_export.path(tmp_path), now=2000000001)
    assert monitor.scan_claude(tmp_path)['quota_source'] == 'statusline'


def test_tick_picks_up_new_browser_file_without_changing_codex_timer(app, tmp_path, monkeypatch):
    import claude_browser as browser
    import monitor
    monkeypatch.setattr(app, '_schedule_tick', lambda: None)
    monkeypatch.setattr(app, 'refresh', lambda: None)
    browser.import_usage(payload(), browser.path(tmp_path), now=2000000000)
    app._render(monitor.scan_codex(tmp_path), monitor.scan_claude(tmp_path))
    previous_update = app._updated_at
    sample = payload()
    sample['rate_limits']['five_hour']['used_percentage'] = 16
    browser.import_usage(sample, browser.path(tmp_path), now=2000000060)
    app._tick()
    assert '残り84%' in app.cl_lbl5.cget('text')
    assert app._last[1]['observed_at'] == 2000000060
    assert app._updated_at == previous_update


def test_oversized_native_message_is_rejected(tmp_path):
    import claude_browser as browser
    output = io.BytesIO()
    browser.serve(io.BytesIO(struct.pack('<I', 1000000)), output, tmp_path/'quota.json')
    assert not json.loads(output.getvalue()[4:])['ok']
    assert not (tmp_path/'quota.json').exists()

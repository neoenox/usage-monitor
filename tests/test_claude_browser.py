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


def test_diagnose_reports_missing_registration(tmp_path, monkeypatch):
    import claude_browser as browser
    monkeypatch.setattr(browser, 'path', lambda home=None: tmp_path / 'missing.json')
    info = browser.diagnose()
    assert info['manifest_exists'] is False
    assert info['quota_exists'] is False
    assert info['observed_at'] is None
    assert '未登録' in browser.diagnose_text(info)


def test_diagnose_reports_fresh_observation(tmp_path, monkeypatch):
    import claude_browser as browser
    target = browser.path(tmp_path)
    browser.import_usage(payload(), target, now=2000000000)
    monkeypatch.setattr(browser, 'path', lambda home=None: target)
    monkeypatch.setattr(browser, 'chrome_running', lambda: True)
    import time
    monkeypatch.setattr(time, 'time', lambda: 2000000100.0)
    info = browser.diagnose()
    assert info['quota_exists'] is True
    assert info['observed_at'] == 2000000000
    assert '分前' in browser.diagnose_text(info) or 'たった今' in browser.diagnose_text(info)


def test_extension_id_defaults_to_pinned_value():
    import claude_browser as browser
    assert browser.DEFAULT_EXTENSION_ID == 'eobplfaccjbfdlolmdjnalbedehgljjl'
    value = browser.extension_id()
    assert isinstance(value, str) and len(value) == 32


def _fake_profile(root, profile, entry):
    import json
    import claude_browser as browser
    target = root / profile / 'Secure Preferences'
    target.parent.mkdir(parents=True, exist_ok=True)
    data = {'extensions': {'settings': {}}}
    if entry is not None:
        data['extensions']['settings'][browser.DEFAULT_EXTENSION_ID] = entry
    target.write_text(json.dumps(data), encoding='utf-8')
    return root


def test_extension_state_distinguishes_missing_disabled_enabled(tmp_path, monkeypatch):
    import json
    import claude_browser as browser
    root = tmp_path / 'User Data'
    _fake_profile(root, 'Default', None)
    _fake_profile(root, 'Profile 2', {'disable_reasons': [1]})
    monkeypatch.setattr(browser, 'chrome_user_data', lambda: root)
    info = browser.extension_state()
    assert info['present'] is True and info['disabled'] is True
    assert 'Profile 2' in info['profiles']
    _fake_profile(root, 'Profile 2', {'disable_reasons': []})
    info = browser.extension_state()
    assert info['present'] is True and info['disabled'] is False
    _fake_profile(root, 'Profile 2', None)
    info = browser.extension_state()
    assert info['present'] is False and info['disabled'] is False
    assert '未導入' in browser.diagnose_text({**browser.diagnose(), 'extension': info})


def test_extension_state_unknown_without_chrome_data(monkeypatch):
    import claude_browser as browser
    monkeypatch.setattr(browser, 'chrome_user_data', lambda: None)
    info = browser.extension_state()
    assert info['present'] is None
    assert '拡張' not in browser.diagnose_text({'manifest_exists': False, 'manifest_origin_ok': False,
                                                'registry_ok': False, 'chrome_running': None,
                                                'observed_at': None, 'age_hours': None, 'extension': info})


def test_extension_state_reports_last_load_time(tmp_path, monkeypatch):
    import time
    import claude_browser as browser
    root = tmp_path / 'User Data'
    unix = 1750000000
    _fake_profile(root, 'Default', {
        'disable_reasons': [],
        'last_update_time': int((unix + 11644473600) * 1_000_000),
    })
    monkeypatch.setattr(browser, 'chrome_user_data', lambda: root)
    info = browser.extension_state()
    assert info['updated_at'] == unix
    text = browser.diagnose_text({'manifest_exists': True, 'manifest_origin_ok': True,
                                  'registry_ok': True, 'chrome_running': True,
                                  'observed_at': None, 'age_hours': None, 'extension': info})
    assert '最終読込' in text
    assert time.strftime('%Y-%m-%d', time.localtime(unix)) in text


def test_extension_state_omits_load_date_when_disabled(tmp_path, monkeypatch):
    import claude_browser as browser
    root = tmp_path / 'User Data'
    _fake_profile(root, 'Default', {'disable_reasons': [1],
                                    'last_update_time': int((1750000000 + 11644473600) * 1_000_000)})
    monkeypatch.setattr(browser, 'chrome_user_data', lambda: root)
    info = browser.extension_state()
    assert info['disabled'] is True and info['updated_at'] == 1750000000
    text = browser.diagnose_text({'manifest_exists': False, 'manifest_origin_ok': False,
                                  'registry_ok': False, 'chrome_running': None,
                                  'observed_at': None, 'age_hours': None, 'extension': info})
    assert '無効' in text
    assert '最終読込' not in text


def test_extension_reload_pending_detects_newer_files(tmp_path, monkeypatch):
    import os
    import claude_browser as browser
    root = tmp_path / 'User Data'
    extdir = tmp_path / 'ext'
    extdir.mkdir()
    manifest = extdir / 'manifest.json'
    manifest.write_text('{}', encoding='utf-8')
    unix = 1750000000
    _fake_profile(root, 'Default', {
        'disable_reasons': [],
        'last_update_time': int((unix + 11644473600) * 1_000_000),
        'path': str(extdir),
    })
    monkeypatch.setattr(browser, 'chrome_user_data', lambda: root)
    os.utime(manifest, (unix + 100, unix + 100))
    assert browser.extension_reload_pending() is True
    os.utime(manifest, (unix - 100, unix - 100))
    assert browser.extension_reload_pending() is False


def test_extension_reload_pending_none_without_path_or_chrome_data(tmp_path, monkeypatch):
    import claude_browser as browser
    root = tmp_path / 'User Data'
    _fake_profile(root, 'Default', {
        'disable_reasons': [],
        'last_update_time': int((1750000000 + 11644473600) * 1_000_000),
    })
    monkeypatch.setattr(browser, 'chrome_user_data', lambda: root)
    assert browser.extension_reload_pending() is None
    monkeypatch.setattr(browser, 'chrome_user_data', lambda: None)
    assert browser.extension_reload_pending() is None


def test_diagnose_text_flags_pending_reload():
    import claude_browser as browser
    text = browser.diagnose_text({
        'manifest_exists': True, 'manifest_origin_ok': True, 'registry_ok': True,
        'chrome_running': True, 'observed_at': None, 'age_hours': None,
        'reload_pending': True,
        'extension': {'present': True, 'disabled': False, 'profiles': ['Default'],
                      'updated_at': 1750000000, 'loaded_path': 'X'},
    })
    assert '再読み込み' in text

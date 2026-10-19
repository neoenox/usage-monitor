import io
import json
import struct
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


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


def test_diagnose_hints_flags_pending_reload():
    import claude_browser as browser
    hints = browser.diagnose_hints({
        'manifest_exists': True, 'manifest_origin_ok': True, 'registry_ok': True,
        'chrome_running': True, 'reload_pending': True, 'age_hours': None,
        'extension': {'present': True, 'disabled': False},
    })
    assert hints == ['拡張の更新が未反映（chrome://extensionsで再読み込み）']


def test_diagnose_hints_order_and_severity():
    import claude_browser as browser
    hints = browser.diagnose_hints({
        'manifest_exists': False, 'manifest_origin_ok': False, 'registry_ok': False,
        'chrome_running': False, 'reload_pending': True, 'age_hours': 2.5,
        'extension': {'present': False, 'disabled': None},
    })
    assert hints[0] == 'manifest未登録'
    assert 'registry未登録' in hints
    assert 'Chromeが閉じています' in hints
    assert '拡張未導入（chrome://extensionsで読み込みが必要）' in hints
    assert '拡張の更新が未反映（chrome://extensionsで再読み込み）' not in hints
    assert '最終観測から2.5時間' in hints


def test_diagnose_hints_disabled_suppresses_reload():
    import claude_browser as browser
    hints = browser.diagnose_hints({
        'manifest_exists': True, 'manifest_origin_ok': True, 'registry_ok': True,
        'chrome_running': True, 'reload_pending': True, 'age_hours': None,
        'extension': {'present': True, 'disabled': True},
    })
    assert hints == ['拡張が無効（chrome://extensionsで有効化）']


def test_diagnose_hints_clean_when_healthy():
    import claude_browser as browser
    hints = browser.diagnose_hints({
        'manifest_exists': True, 'manifest_origin_ok': True, 'registry_ok': True,
        'chrome_running': True, 'reload_pending': False, 'age_hours': 0.2,
        'extension': {'present': True, 'disabled': False},
    })
    assert hints == []


# --- CLI 入口 (main / register) と、防御的な戻り値 ---------------------------
# claude_browser.py は 74% で、未到達がちょうど「利用者が実行する入口」に
# 固まっていた: main() の分岐、register() (拡張のセットアップ手順そのもの)、
# extension_id()/host_exe() のフォールバック、そして diagnose() の防御経路。


class _FakeStd:
    """main() が触る stdin/stdout の最小インタフェース (buffer と fileno)。"""

    def __init__(self, data: bytes = b'', fd: int = 0):
        self.buffer = io.BytesIO(data)
        self._fd = fd

    def fileno(self) -> int:
        return self._fd


class _FakeKey:
    def __init__(self, path):
        self.path = path

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeWinreg:
    """register()/diagnose() が使う範囲だけの winreg。実レジストリを触らない。"""

    HKEY_CURRENT_USER = 0x80000001
    REG_SZ = 1

    def __init__(self, value=None):
        self.value = value
        self.opened = []
        self.written = []

    def OpenKey(self, root, path):
        self.opened.append(path)
        if self.value is None:
            raise FileNotFoundError('no such key')
        return _FakeKey(path)

    def QueryValueEx(self, key, name):
        return self.value, self.REG_SZ

    def CreateKey(self, root, path):
        return _FakeKey(path)

    def SetValueEx(self, key, name, reserved, kind, value):
        self.written.append((key.path, name, reserved, kind, value))


def test_main_serves_the_native_protocol_when_the_extension_launches_it(monkeypatch, tmp_path):
    import claude_browser as browser
    target = tmp_path / 'claude-browser-quota.json'
    monkeypatch.setattr(browser, 'path', lambda home=None: target)
    raw = json.dumps(payload()).encode('utf-8')
    stdin = _FakeStd(struct.pack('<I', len(raw)) + raw, fd=0)
    stdout = _FakeStd(fd=1)
    modes = []
    if sys.platform == 'win32':
        import msvcrt
        import os
        monkeypatch.setattr(msvcrt, 'setmode', lambda fd, mode: modes.append((fd, mode)))
    monkeypatch.setattr(sys, 'stdin', stdin)
    monkeypatch.setattr(sys, 'stdout', stdout)
    monkeypatch.setattr(sys, 'argv', ['claude_browser.py', 'chrome-extension://eobplfaccjbfdlolmdjnalbedehgljjl/'])

    browser.main()

    assert json.loads(stdout.buffer.getvalue()[4:]) == {'ok': True}
    text = json.loads(target.read_text(encoding='utf-8'))
    assert text['windows']['five_hour']['utilization'] == 13
    if sys.platform == 'win32':
        # ネイティブメッセージはバイナリ。改行変換が入るとフレームが壊れる。
        assert modes == [(0, os.O_BINARY), (1, os.O_BINARY)]


def test_main_register_dispatches_to_register(monkeypatch):
    import claude_browser as browser
    seen = []
    monkeypatch.setattr(browser, 'register', lambda extension_id: seen.append(extension_id))
    monkeypatch.setattr(sys, 'argv', ['claude_browser.py', '--register', 'a' * 32])
    browser.main()
    assert seen == ['a' * 32]


def test_main_register_rejects_an_invalid_extension_id(monkeypatch, tmp_path):
    import claude_browser as browser
    monkeypatch.setitem(sys.modules, 'winreg', _FakeWinreg())
    monkeypatch.setattr(browser, 'path', lambda home=None: tmp_path / 'claude-browser-quota.json')
    monkeypatch.setattr(sys, 'argv', ['claude_browser.py', '--register', 'not-an-id'])
    with pytest.raises(ValueError):
        browser.main()
    assert not (tmp_path / 'browser-native-host.json').exists()


def test_main_imports_a_quota_file(monkeypatch, tmp_path):
    import claude_browser as browser
    target = tmp_path / 'claude-browser-quota.json'
    monkeypatch.setattr(browser, 'path', lambda home=None: target)
    source = tmp_path / 'incoming.json'
    source.write_text(json.dumps(payload()), encoding='utf-8')
    monkeypatch.setattr(sys, 'argv', ['claude_browser.py', '--import', str(source)])

    browser.main()

    observed = json.loads(target.read_text(encoding='utf-8'))
    assert observed['windows']['seven_day']['utilization'] == 88


@pytest.mark.parametrize('argv', [
    ['claude_browser.py'],
    ['claude_browser.py', 'evil.exe'],
    ['claude_browser.py', '--unknown', 'value'],
])
def test_main_rejects_a_direct_launch(monkeypatch, argv):
    import claude_browser as browser
    monkeypatch.setattr(sys, 'argv', argv)
    with pytest.raises(SystemExit) as excinfo:
        browser.main()
    assert 'Launch through the browser extension' in str(excinfo.value)


def test_cli_without_arguments_exits_with_a_message(run_process):
    proc = run_process([sys.executable, 'claude_browser.py'], cwd=ROOT, expect=None)
    assert proc.returncode != 0
    assert 'Launch through the browser extension' in proc.stdout + proc.stderr


def test_register_writes_the_manifest_and_the_current_user_key(monkeypatch, tmp_path):
    import claude_browser as browser
    fake = _FakeWinreg()
    monkeypatch.setitem(sys.modules, 'winreg', fake)
    monkeypatch.setattr(browser, 'path', lambda home=None: tmp_path / 'claude-browser-quota.json')
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'executable', str(tmp_path / 'host' / 'usage-monitor-browser-host.exe'))

    browser.register('a' * 32)

    manifest = tmp_path / 'browser-native-host.json'
    data = json.loads(manifest.read_text(encoding='utf-8'))
    assert data['name'] == browser.HOST
    assert data['type'] == 'stdio'
    assert data['path'] == str((tmp_path / 'host' / 'usage-monitor-browser-host.exe').resolve())
    assert data['allowed_origins'] == ['chrome-extension://' + 'a' * 32 + '/']
    path_used, name, reserved, kind, value = fake.written[0]
    assert path_used == rf'Software\Google\Chrome\NativeMessagingHosts\{browser.HOST}'
    assert (name, reserved) == ('', 0) and kind == fake.REG_SZ
    assert value == str(manifest.resolve())


def test_register_refuses_to_write_from_an_unfrozen_run(monkeypatch, tmp_path):
    import claude_browser as browser
    fake = _FakeWinreg()
    monkeypatch.setitem(sys.modules, 'winreg', fake)
    monkeypatch.setattr(browser, 'path', lambda home=None: tmp_path / 'claude-browser-quota.json')
    monkeypatch.setattr(sys, 'frozen', False, raising=False)

    with pytest.raises(ValueError):
        browser.register('a' * 32)

    assert not (tmp_path / 'browser-native-host.json').exists()
    assert fake.written == []


def test_extension_id_falls_back_to_the_pinned_value(monkeypatch, tmp_path):
    import claude_browser as browser
    monkeypatch.setattr(browser, '__file__', str(tmp_path / 'claude_browser.py'))
    assert browser.extension_id() == browser.DEFAULT_EXTENSION_ID      # ファイルが無い
    ext = tmp_path / 'browser-extension'
    ext.mkdir()
    (ext / 'extension-id.txt').write_text('  \n', encoding='utf-8')
    assert browser.extension_id() == browser.DEFAULT_EXTENSION_ID      # 空
    (ext / 'extension-id.txt').write_text('a' * 32, encoding='utf-8')
    assert browser.extension_id() == 'a' * 32


def test_host_exe_depends_on_the_run_mode(monkeypatch, tmp_path):
    import claude_browser as browser
    monkeypatch.setattr(sys, 'frozen', False, raising=False)
    assert browser.host_exe() == Path(browser.__file__).resolve().parent / 'dist' / 'usage-monitor-browser-host.exe'
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    host = tmp_path / 'host' / 'usage-monitor-browser-host.exe'
    monkeypatch.setattr(sys, 'executable', str(host))
    assert browser.host_exe() == host.resolve()


def test_chrome_user_data_is_none_without_local_app_data(monkeypatch):
    import claude_browser as browser
    monkeypatch.delenv('LOCALAPPDATA', raising=False)
    assert browser.chrome_user_data() is None


def test_import_usage_requires_a_rate_limits_mapping(tmp_path):
    import claude_browser as browser
    for data in ([], {'rate_limits': 'x'}, 'nope'):
        with pytest.raises(ValueError, match='Missing rate limits'):
            browser.import_usage(data, tmp_path / 'quota.json')
    assert not (tmp_path / 'quota.json').exists()


def test_truncated_native_message_is_rejected(tmp_path):
    import claude_browser as browser
    output = io.BytesIO()
    browser.serve(io.BytesIO(b'\x02\x00'), output, tmp_path / 'quota.json')
    assert json.loads(output.getvalue()[4:]) == {
        'ok': False, 'error': '使用率データを取り込めませんでした'}
    assert not (tmp_path / 'quota.json').exists()


def test_extension_state_skips_unreadable_profiles(monkeypatch, tmp_path):
    import claude_browser as browser
    root = tmp_path / 'User Data'
    _fake_profile(root, 'Default', None)
    (root / 'Default' / 'Secure Preferences').write_text('{"extensions": "not a mapping"}',
                                                         encoding='utf-8')
    monkeypatch.setattr(browser, 'chrome_user_data', lambda: root)
    assert browser.extension_state()['present'] is False      # 壊れた形は読み飛ばす

    def boom():
        raise OSError('chrome data unreadable')

    monkeypatch.setattr(browser, 'chrome_user_data', boom)
    assert browser.extension_state()['present'] is None


def test_newest_mtime_handles_missing_and_unreadable_files(monkeypatch, tmp_path):
    import os
    import claude_browser as browser
    assert browser._newest_mtime(tmp_path / 'missing') is None

    good = tmp_path / 'good.txt'
    good.write_text('x', encoding='utf-8')
    bad = tmp_path / 'bad.txt'
    bad.write_text('x', encoding='utf-8')
    real_stat = Path.stat

    def flaky_stat(self, *args, **kwargs):
        if self == bad:
            raise OSError('disappeared between walk and stat')
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, 'stat', flaky_stat)
    assert browser._newest_mtime(tmp_path) == pytest.approx(good.stat().st_mtime)

    def broken_walk(*args, **kwargs):
        raise OSError('tree unreadable')

    monkeypatch.setattr(os, 'walk', broken_walk)
    assert browser._newest_mtime(tmp_path) is None


def test_extension_reload_pending_unknown_for_missing_dir_or_garbage(tmp_path):
    import claude_browser as browser
    assert browser.extension_reload_pending(
        {'updated_at': 1750000000, 'loaded_path': str(tmp_path / 'gone')}) is None
    assert browser.extension_reload_pending(object()) is None


def test_chrome_running_is_unknown_off_windows(monkeypatch):
    import claude_browser as browser
    monkeypatch.setattr(sys, 'platform', 'linux')
    assert browser.chrome_running() is None


@pytest.mark.skipif(sys.platform != 'win32', reason="tasklist は Windows のみ")
def test_chrome_running_is_unknown_when_tasklist_fails(monkeypatch):
    import subprocess
    import claude_browser as browser

    def boom(*args, **kwargs):
        raise OSError('tasklist unavailable')

    monkeypatch.setattr(subprocess, 'run', boom)
    assert browser.chrome_running() is None


def test_diagnose_survives_every_probe_failing(monkeypatch):
    import claude_browser as browser

    def boom(*args, **kwargs):
        raise OSError('probe unavailable')

    monkeypatch.setattr(browser, 'extension_state', boom)
    monkeypatch.setattr(browser, 'extension_reload_pending', boom)
    monkeypatch.setattr(browser, 'path', boom)
    monkeypatch.setattr(browser, 'chrome_running', lambda: None)

    info = browser.diagnose()

    assert info['extension'] == {'present': None, 'disabled': None, 'profiles': [],
                                 'updated_at': None, 'loaded_path': None}
    assert info['reload_pending'] is None
    assert info['manifest_exists'] is False and info['manifest_path'] is None
    assert info['manifest_path_exists'] is False and info['manifest_origin_ok'] is False
    assert info['quota_exists'] is False and info['observed_at'] is None
    assert info['age_hours'] is None


def test_diagnose_flags_a_corrupt_manifest_and_quota_file(monkeypatch, tmp_path):
    import claude_browser as browser
    (tmp_path / 'browser-native-host.json').write_text('{oops', encoding='utf-8')
    target = tmp_path / 'claude-browser-quota.json'
    target.write_text('{oops', encoding='utf-8')
    monkeypatch.setattr(browser, 'path', lambda home=None: target)
    monkeypatch.setattr(browser, 'chrome_user_data', lambda: None)
    monkeypatch.setattr(browser, 'chrome_running', lambda: None)

    info = browser.diagnose()

    assert info['manifest_exists'] is True
    assert info['manifest_path'] is None and info['manifest_origin_ok'] is False
    assert info['quota_exists'] is False and info['observed_at'] is None


def test_diagnose_honours_a_well_formed_manifest(monkeypatch, tmp_path):
    import claude_browser as browser
    manifest = tmp_path / 'browser-native-host.json'
    manifest.write_text(json.dumps({
        'path': str(Path(sys.executable)),
        'allowed_origins': [f'chrome-extension://{browser.extension_id()}/'],
    }), encoding='utf-8')
    monkeypatch.setattr(browser, 'path', lambda home=None: tmp_path / 'claude-browser-quota.json')
    monkeypatch.setattr(browser, 'chrome_user_data', lambda: None)
    monkeypatch.setattr(browser, 'chrome_running', lambda: True)

    info = browser.diagnose()

    assert info['manifest_exists'] is True
    assert info['manifest_path_exists'] is True
    assert info['manifest_origin_ok'] is True
    assert browser.diagnose_text(info).startswith('manifest: OK')


@pytest.mark.parametrize('registered', [True, False])
def test_diagnose_reports_the_registry_state(monkeypatch, tmp_path, registered):
    import claude_browser as browser
    manifest = str(tmp_path / 'browser-native-host.json')
    fake = _FakeWinreg(value=manifest if registered else None)
    monkeypatch.setitem(sys.modules, 'winreg', fake)
    monkeypatch.setattr(sys, 'platform', 'win32')
    monkeypatch.setattr(browser, 'path', lambda home=None: tmp_path / 'claude-browser-quota.json')
    monkeypatch.setattr(browser, 'chrome_user_data', lambda: None)
    monkeypatch.setattr(browser, 'chrome_running', lambda: None)

    info = browser.diagnose()

    assert fake.opened == [rf'Software\Google\Chrome\NativeMessagingHosts\{browser.HOST}']
    assert info['registry_ok'] is registered
    assert info['registry_value'] == (manifest if registered else None)


def test_diagnose_survives_a_broken_registry_probe(monkeypatch, tmp_path):
    import claude_browser as browser

    class BrokenWinreg:
        HKEY_CURRENT_USER = 0

        def OpenKey(self, *args):
            raise ValueError('malformed hive')

    monkeypatch.setitem(sys.modules, 'winreg', BrokenWinreg())
    monkeypatch.setattr(sys, 'platform', 'win32')
    monkeypatch.setattr(browser, 'path', lambda home=None: tmp_path / 'claude-browser-quota.json')
    monkeypatch.setattr(browser, 'chrome_user_data', lambda: None)
    monkeypatch.setattr(browser, 'chrome_running', lambda: None)

    info = browser.diagnose()

    assert info['registry_ok'] is False and info['registry_value'] is None


def test_diagnose_registry_unknown_off_windows(monkeypatch, tmp_path):
    import claude_browser as browser
    monkeypatch.setattr(sys, 'platform', 'linux')
    monkeypatch.setattr(browser, 'path', lambda home=None: tmp_path / 'claude-browser-quota.json')
    monkeypatch.setattr(browser, 'chrome_user_data', lambda: None)
    monkeypatch.setattr(browser, 'chrome_running', lambda: None)

    info = browser.diagnose()

    assert info['registry_ok'] is None and info['registry_value'] is None


def test_diagnose_does_not_raise_on_an_absurd_observation_time(monkeypatch, tmp_path):
    """JSONの整数リテラルは任意精度: 壊れた観測時刻でも diagnose は落ちない。"""
    import claude_browser as browser
    target = tmp_path / 'claude-browser-quota.json'
    target.write_text(json.dumps({'observed_at': int('1' + '0' * 400)}), encoding='utf-8')
    monkeypatch.setattr(browser, 'path', lambda home=None: target)
    monkeypatch.setattr(browser, 'chrome_user_data', lambda: None)
    monkeypatch.setattr(browser, 'chrome_running', lambda: None)

    info = browser.diagnose()

    assert info['quota_exists'] is True
    assert info['observed_at'] is not None
    assert info['age_hours'] is None            # float() できないので不明


def test_diagnose_text_reports_the_age_in_minutes_and_hours():
    import claude_browser as browser
    base = {'manifest_exists': True, 'manifest_origin_ok': True, 'registry_ok': True,
            'chrome_running': True, 'extension': {'present': True, 'disabled': False}}
    assert '約20分前' in browser.diagnose_text({**base, 'age_hours': 20 / 60})
    assert '約2.5時間前' in browser.diagnose_text({**base, 'age_hours': 2.5})

import copy
import time

import gui
import monitor as m
import usage_cache as cache


def snapshots():
    future = int(time.time()) + 3600
    return ({'has_rate': True, 'usage_status': 'ok', 'rate_limits': {
        'primary': {'used_percent': 26, 'resets_at': future},
        'secondary': {'used_percent': 21, 'resets_at': future}}},
        {'oauth': {'status': 'ok', 'five_hour': {'utilization': 29, 'resets_at': '2999-01-01T00:00:00Z'},
                   'seven_day': {'utilization': 36, 'resets_at': '2999-01-01T00:00:00Z'}}})


def test_restart_offline_retains_both_providers(tmp_path):
    path = tmp_path / 'last.json'
    c, cl = snapshots()
    cache.apply(c, cl, path, now=100)
    c, cl = cache.apply({'has_rate': False, 'usage_status': 'error'}, {'oauth': {'status': 'error'}}, path, now=200)
    assert c['has_rate'] and c['quota_cached'] and c['observed_at'] == 100
    assert c['rate_limits']['primary']['used_percent'] == 26
    assert cl['quota_cached'] and cl['oauth']['five_hour']['utilization'] == 29
    assert cl['observed_at'] == 100
    metrics, _ = gui.history_snapshot(c, 26, 21)
    assert metrics == {}


def test_expired_cached_value_not_reset(tmp_path):
    c, cl = snapshots()
    c['rate_limits']['primary']['resets_at'] = 1
    cl['oauth']['five_hour']['resets_at'] = '2000-01-01T00:00:00Z'
    cache.apply(c, cl, tmp_path/'last.json')
    c, cl = cache.apply({'usage_status': 'error'}, {'oauth': {'status': 'error'}}, tmp_path/'last.json')
    c, cl = m.normalize_snapshot(c, cl)
    assert c['has_rate'] and c['rate_limits']['primary']['used_percent'] == 26
    assert cl['oauth']['five_hour']['utilization'] == 29
    assert 'リセット前' in cache.label(26, 1, c['observed_at'])


def test_recovery_replaces_cache_without_mutating_inputs(tmp_path):
    c, cl = snapshots()
    original = copy.deepcopy(c)
    cache.apply(c, cl, tmp_path/'last.json', now=100)
    c['rate_limits']['primary']['used_percent'] = 40
    fresh, _ = cache.apply(c, cl, tmp_path/'last.json', now=300)
    assert not fresh.get('quota_cached') and fresh['observed_at'] == 300
    assert original['rate_limits']['primary']['used_percent'] == 26


def test_corrupt_cache_and_no_success_stay_unavailable(tmp_path):
    path = tmp_path/'last.json'
    path.write_text('broken')
    c, cl = cache.apply({'has_rate': False, 'usage_status': 'error'}, {'oauth': {'status': 'error'}}, path)
    assert not c['has_rate'] and cl['oauth']['status'] == 'error'


def test_cached_values_render_and_tick_without_new_history(app, fake_home, tmp_path, monkeypatch):
    c = m.scan_codex(fake_home)
    cl = m.scan_claude(fake_home)
    live_c, live_cl = snapshots()
    c.update(live_c)
    cl.update(live_cl)
    cl.pop('quota_source', None)  # Simulate the legacy direct-poll cache format.
    path = tmp_path/'last.json'
    cache.apply(c, cl, path)
    c['has_rate'] = False
    c['usage_status'] = 'error'
    cl['oauth'] = {'status': 'error'}
    c, cl = cache.apply(c, cl, path)
    import history
    records = []
    monkeypatch.setattr(history, 'record', lambda *a, **kw: records.append(a))
    app._render(c, cl)
    assert records == []
    assert float(app.bar5['value']) == 74
    assert float(app.cl_bar5['value']) == 71
    assert '前回取得値' in app.lbl5.cget('text')
    assert '前回取得値' in app.cl_lbl5.cget('text')
    app._tick()
    assert '前回取得値' in app.lbl5.cget('text')
    assert '予測' not in app.lbl5.cget('text')
    assert '前回取得値' in gui.tray_tooltip(c, cl)


def test_cached_values_do_not_send_alerts(tmp_path):
    from tests.test_e2e import _FakeTray
    c, cl = snapshots()
    c['rate_limits']['primary']['used_percent'] = 99
    cl['oauth']['five_hour']['utilization'] = 99
    path = tmp_path/'last.json'
    cache.apply(c, cl, path)
    c, cl = cache.apply({'usage_status': 'error'}, {'oauth': {'status': 'error'}}, path)
    controller = object.__new__(gui.TrayController)
    controller.tray = _FakeTray()
    controller.notified = {}
    controller._check_alerts(c, cl)
    assert controller.tray.balloons == []


def test_cache_contains_only_quota_fields(tmp_path):
    c, cl = snapshots()
    c['secret'] = cl['oauth']['token'] = 'do-not-store'
    path = tmp_path/'last.json'
    cache.apply(c, cl, path)
    assert 'do-not-store' not in path.read_text()

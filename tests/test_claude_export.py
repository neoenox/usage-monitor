import json
import pytest
import claude_export as c


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

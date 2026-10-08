import monitor


def test_scan_claude_uses_direct_fetch_not_statusline(tmp_path, monkeypatch):
    monkeypatch.setattr(monitor, 'fetch_claude_oauth', lambda home, **kw: {'status': 'ok', 'five_hour': {'utilization': 7}})
    result = monitor.scan_claude(tmp_path)
    assert result['oauth']['status'] == 'ok'
    assert result['oauth']['five_hour']['utilization'] == 7
    assert result.get('quota_source') != 'statusline'
    assert not result.get('quota_cached')

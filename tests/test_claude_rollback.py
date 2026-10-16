import monitor


def test_scan_claude_never_directly_fetches_usage(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('independent authentication or OAuth request')
    monkeypatch.setattr(monitor, 'fetch_claude_oauth', forbidden)
    result = monitor.scan_claude(tmp_path)
    assert result['oauth']['status'] == 'missing_token'
    assert result.get('quota_source') == 'statusline'
    assert not result.get('quota_cached')

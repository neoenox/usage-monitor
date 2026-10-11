"""Statusline integration does not require monitoring OAuth cooldowns."""
import gui


def test_missing_observation_does_not_request_daily_relogin():
    _, text = gui.setup_guidance({}, {'oauth': {'status': 'missing_token'}, 'quota_source': 'statusline'})
    assert 'statusline' in text
    assert 'claude auth login' not in text

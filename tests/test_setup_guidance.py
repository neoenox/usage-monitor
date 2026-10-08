import gui


def test_setup_guidance_distinguishes_install_login_observation():
    cx, cl = gui.setup_guidance({'usage_status': 'missing_cli'}, {'oauth': {'status': 'missing_token'}})
    assert 'インストール' in cx and 'ログイン' in cx
    assert 'claude auth login' in cl and '未取得' in cl
    cx, cl = gui.setup_guidance({'usage_status': 'error', 'usage_detail': 'not logged in'}, {'oauth': {'status': 'ok'}, 'quota_source': 'statusline'})
    assert 'not logged in' in cx and 'codex login' in cx
    assert '観測済み' in cl and 'ログイン済み' not in cl
    cx, _ = gui.setup_guidance({'usage_status': 'ok'}, {})
    assert '取得成功' in cx

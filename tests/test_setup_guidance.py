import gui


def test_claude_four_setup_states():
    assert gui.claude_setup_state({}, claude_code=False) == 'no_claude_code'
    assert gui.claude_setup_state({}, claude_code=True, statusline_configured=False) == 'statusline_missing'
    assert gui.claude_setup_state({}, claude_code=True, statusline_configured=True) == 'awaiting_observation'
    assert gui.claude_setup_state({'oauth': {'status': 'ok'}}) == 'receiving'
    assert gui.claude_setup_state({}) == 'unknown'


def test_setup_guidance_renders_four_claude_states():
    _, no_code = gui.setup_guidance({'usage_status': 'ok'}, {}, claude_code=False)
    assert 'Claude Code未検出' in no_code
    _, missing = gui.setup_guidance({'usage_status': 'ok'}, {}, claude_code=True, statusline_configured=False)
    assert 'statusline未設定' in missing
    _, waiting = gui.setup_guidance({'usage_status': 'ok'}, {}, claude_code=True, statusline_configured=True)
    assert '観測待ち' in waiting
    _, receiving = gui.setup_guidance({'usage_status': 'ok'}, {'oauth': {'status': 'ok'}},
                                      claude_code=True, statusline_configured=True)
    assert '観測済み' in receiving


def test_setup_guidance_distinguishes_install_login_observation():
    cx, cl = gui.setup_guidance({'usage_status': 'missing_cli'}, {'oauth': {'status': 'missing_token'}})
    assert 'インストール' in cx and 'ログイン' in cx
    assert 'statusline' in cl and 'データ待ち' in cl
    cx, cl = gui.setup_guidance({'usage_status': 'error', 'usage_detail': 'not logged in'}, {'oauth': {'status': 'ok'}, 'quota_source': 'statusline'})
    assert 'not logged in' in cx and 'codex login' in cx
    assert '観測済み' in cl and 'ログイン済み' not in cl
    cx, _ = gui.setup_guidance({'usage_status': 'ok'}, {})
    assert '取得成功' in cx

import json
import pytest
import claude_setup as s


def test_no_consent_no_change(tmp_path):
    target = tmp_path/'settings.json'
    with pytest.raises(ValueError):
        s.install(target, 'monitor --claude-export', consent=False)
    assert not target.exists()


def test_existing_statusline_requires_explicit_replace_and_restores(tmp_path):
    target = tmp_path/'settings.json'
    original = {'statusLine': {'type': 'command', 'command': 'old'}, 'theme': 'dark'}
    target.write_text(json.dumps(original))
    with pytest.raises(ValueError):
        s.install(target, 'monitor --claude-export', consent=True)
    assert json.loads(target.read_text()) == original
    s.install(target, 'monitor --claude-export', consent=True, replace_existing=True)
    changed = json.loads(target.read_text())
    changed['theme'] = 'light'
    target.write_text(json.dumps(changed))
    s.restore(target)
    assert json.loads(target.read_text()) == {'statusLine': original['statusLine'], 'theme': 'light'}


def test_restore_does_not_overwrite_new_user_statusline(tmp_path):
    target = tmp_path/'settings.json'
    s.install(target, 'monitor --claude-export', consent=True)
    target.write_text(json.dumps({'statusLine': {'command': 'new'}}))
    with pytest.raises(ValueError):
        s.restore(target)
    assert json.loads(target.read_text())['statusLine']['command'] == 'new'

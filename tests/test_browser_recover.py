"""Idle-gated, loop-safe browser linkage recovery."""
import pytest


def diag(**over):
    base = {'manifest_exists': True, 'manifest_origin_ok': True, 'registry_ok': True,
            'age_hours': 0.1, 'extension': {'present': True, 'disabled': False, 'profiles': ['Default']}}
    base.update(over)
    return base


def test_classify_maps_each_failure():
    import browser_recover as r
    assert r.classify(diag()) == 'healthy'
    assert r.classify(diag(manifest_exists=False)) == 'host_missing'
    assert r.classify(diag(registry_ok=False)) == 'host_missing'
    assert r.classify(diag(extension={'present': False, 'disabled': False, 'profiles': []})) == 'extension_missing'
    assert r.classify(diag(extension={'present': True, 'disabled': True, 'profiles': ['Default']})) == 'extension_disabled'
    assert r.classify(diag(age_hours=5.0)) == 'observation_stale'
    assert r.classify(None) == 'unknown'


def test_healthy_takes_no_action(tmp_path, monkeypatch):
    import browser_recover as r
    import claude_browser
    monkeypatch.setattr(r, 'app_dir', lambda: tmp_path)
    monkeypatch.setattr(claude_browser, 'diagnose', lambda *a, **k: diag())
    assert r.maybe_auto_repair(now=1000.0) == {'acted': False, 'reason': 'healthy', 'class': 'healthy'}
    assert not (tmp_path / r.ATTEMPT_NAME).exists()


def test_host_repair_requires_approval_and_cools_down(tmp_path, monkeypatch):
    import browser_recover as r
    import claude_browser
    monkeypatch.setattr(r, 'app_dir', lambda: tmp_path)
    monkeypatch.setattr(claude_browser, 'diagnose',
                        lambda *a, **k: diag(manifest_exists=False, registry_ok=False))
    calls = []
    monkeypatch.setattr(r, '_run_host_register', lambda eid: calls.append(eid) or True)
    # No approval marker: no action, no cooldown recorded.
    out = r.maybe_auto_repair(now=2000.0)
    assert out == {'acted': False, 'reason': 'no_approval', 'class': 'host_missing'}
    assert calls == [] and not (tmp_path / r.ATTEMPT_NAME).exists()
    r.mark_approved()
    out = r.maybe_auto_repair(now=2000.0)
    assert out == {'acted': True, 'reason': 'host_reregistered', 'class': 'host_missing'}
    assert len(calls) == 1
    # Second call inside cooldown: no repeated action (no loop).
    out = r.maybe_auto_repair(now=2000.0 + 3600)
    assert out == {'acted': False, 'reason': 'cooldown', 'class': 'host_missing'}
    assert len(calls) == 1


def test_extension_states_defer_without_driving_ui(tmp_path, monkeypatch):
    import browser_recover as r
    import claude_browser
    monkeypatch.setattr(r, 'app_dir', lambda: tmp_path)
    monkeypatch.setattr(claude_browser, 'diagnose',
                        lambda *a, **k: diag(extension={'present': False, 'disabled': False, 'profiles': []}))
    monkeypatch.setattr(r, 'idle_ms', lambda: 100.0)
    out = r.maybe_auto_repair(now=3000.0)
    assert out == {'acted': False, 'reason': 'user_active', 'class': 'extension_missing'}
    assert not (tmp_path / r.ATTEMPT_NAME).exists()


def test_extension_missing_triggers_driver_once(tmp_path, monkeypatch):
    import sys
    import browser_recover as r
    import claude_browser
    monkeypatch.setattr(r, 'app_dir', lambda: tmp_path)
    monkeypatch.setattr(claude_browser, 'diagnose',
                        lambda *a, **k: diag(extension={'present': False, 'disabled': False, 'profiles': []}))
    monkeypatch.setattr(r, 'idle_ms', lambda: 60000.0)
    calls = []
    monkeypatch.setattr(r, '_run_gui_load', lambda *a: calls.append(a) or (True, 'loaded'))
    out = r.maybe_auto_repair(now=3000.0)
    assert out == {'acted': True, 'reason': 'extension_reloaded', 'class': 'extension_missing'}
    assert len(calls) == 1
    out = r.maybe_auto_repair(now=3000.0 + 3600)
    assert out['reason'] == 'cooldown' and len(calls) == 1


def test_extension_driver_abort_maps_to_user_active(tmp_path, monkeypatch):
    import browser_recover as r
    import claude_browser
    monkeypatch.setattr(r, 'app_dir', lambda: tmp_path)
    monkeypatch.setattr(claude_browser, 'diagnose',
                        lambda *a, **k: diag(extension={'present': True, 'disabled': True, 'profiles': ['Default']}))
    monkeypatch.setattr(r, 'idle_ms', lambda: 60000.0)
    monkeypatch.setattr(r, '_run_gui_load', lambda *a: (False, 'aborted_user_active'))
    out = r.maybe_auto_repair(now=3000.0)
    assert out == {'acted': False, 'reason': 'user_active', 'class': 'extension_disabled'}


def test_extension_driver_unavailable_without_script(tmp_path, monkeypatch):
    import browser_recover as r
    import claude_browser
    monkeypatch.setattr(r, 'app_dir', lambda: tmp_path)
    monkeypatch.setattr(claude_browser, 'diagnose',
                        lambda *a, **k: diag(extension={'present': False, 'disabled': False, 'profiles': []}))
    monkeypatch.setattr(r, 'idle_ms', lambda: 60000.0)
    monkeypatch.setattr(r, 'driver_script', lambda: None)
    out = r.maybe_auto_repair(now=3000.0)
    assert out == {'acted': False, 'reason': 'needs_manual_load', 'class': 'extension_missing'}


def test_user_active_unknown_is_conservative(monkeypatch):
    import browser_recover as r
    monkeypatch.setattr(r, 'idle_ms', lambda: None)
    assert r.user_active() is None


def test_log_never_carries_payloads(tmp_path, monkeypatch):
    import browser_recover as r
    import claude_browser
    monkeypatch.setattr(r, 'app_dir', lambda: tmp_path)
    monkeypatch.setattr(claude_browser, 'diagnose',
                        lambda *a, **k: diag(extension={'present': False, 'disabled': False, 'profiles': []}))
    monkeypatch.setattr(r, 'idle_ms', lambda: 100.0)
    r.maybe_auto_repair(now=4000.0)
    text = (tmp_path / r.LOG_NAME).read_text(encoding='utf-8')
    assert 'CANARY-SECRET-9f8e7d' not in text
    assert 'user_active' in text

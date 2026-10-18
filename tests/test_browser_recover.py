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
    monkeypatch.setattr(r, '_can_drive_gui', lambda: True)
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
    monkeypatch.setattr(r, '_can_drive_gui', lambda: True)
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


class _Proc:
    """Stand-in for subprocess.CompletedProcess."""

    def __init__(self, returncode=0, stdout=''):
        self.returncode = returncode
        self.stdout = stdout


def test_app_dir_uses_localappdata_with_a_home_fallback(tmp_path, monkeypatch):
    import browser_recover as r
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'lad'))
    assert r.app_dir() == tmp_path / 'lad' / 'usage-monitor'
    monkeypatch.delenv('LOCALAPPDATA', raising=False)
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv('USERPROFILE', str(tmp_path))
    assert r.app_dir() == tmp_path / 'usage-monitor'


def test_idle_measurement_is_optional_but_never_raises():
    import browser_recover as r
    value = r.idle_ms()
    assert value is None or (isinstance(value, float) and value >= 0.0)


def test_user_active_boundary(monkeypatch):
    import browser_recover as r
    limit = r.IDLE_THRESHOLD_MIN * 60 * 1000
    monkeypatch.setattr(r, 'idle_ms', lambda: limit - 1)
    assert r.user_active() is True
    monkeypatch.setattr(r, 'idle_ms', lambda: limit)
    assert r.user_active() is False
    assert r.user_active(threshold_min=0) is False


def test_log_event_appends_state_only_and_survives_os_errors(tmp_path, monkeypatch):
    import browser_recover as r
    monkeypatch.setattr(r, 'app_dir', lambda: tmp_path)
    r.log_event('repair_skipped', 'host_missing/no_approval')
    r.log_event('repair_deferred')
    lines = (tmp_path / r.LOG_NAME).read_text(encoding='utf-8').splitlines()
    assert len(lines) == 2
    assert lines[0].endswith('repair_skipped host_missing/no_approval')
    assert lines[1].endswith('repair_deferred')
    assert 'CANARY-SECRET-9f8e7d' not in '\n'.join(lines)
    blocker = tmp_path / 'blocker'
    blocker.write_text('not a directory', encoding='utf-8')
    monkeypatch.setattr(r, 'app_dir', lambda: blocker / 'nested')
    r.log_event('repair_deferred', 'unwritable')  # swallowed, never raises


def test_markers_survive_an_unwritable_app_dir(tmp_path, monkeypatch):
    import browser_recover as r
    blocker = tmp_path / 'blocker'
    blocker.write_text('not a directory', encoding='utf-8')
    monkeypatch.setattr(r, 'app_dir', lambda: blocker / 'nested')
    r.mark_approved()
    r._record_attempt(1234.0)
    assert r.approval_given() is False
    assert r._last_attempt(1234.0) is None


def test_attempt_marker_round_trip_and_unusable_content(tmp_path, monkeypatch):
    import browser_recover as r
    monkeypatch.setattr(r, 'app_dir', lambda: tmp_path)
    (tmp_path / r.ATTEMPT_NAME).write_text('not-a-timestamp', encoding='utf-8')
    assert r._last_attempt(1.0) is None
    r._record_attempt(1500.5)
    assert r._last_attempt(1.0) == 1500.5
    assert r.approval_given() is False


def test_classify_ignores_an_unusable_age():
    import browser_recover as r
    assert r.classify(diag(age_hours='n/a')) == 'healthy'
    assert r.classify(diag(age_hours=None)) == 'healthy'
    assert r.classify({'extension': {}, 'manifest_exists': True, 'manifest_origin_ok': True,
                       'registry_ok': None, 'age_hours': 0}) == 'healthy'


def test_diagnose_failure_is_reported_not_raised(tmp_path, monkeypatch):
    import browser_recover as r
    import claude_browser
    monkeypatch.setattr(r, 'app_dir', lambda: tmp_path)

    def boom(*a, **k):
        raise RuntimeError('diagnose blew up')

    monkeypatch.setattr(claude_browser, 'diagnose', boom)
    assert r.maybe_auto_repair(now=5000.0) == {'acted': False, 'reason': 'diagnose_failed', 'class': 'unknown'}


def test_can_drive_gui_matches_the_platform():
    import sys
    import browser_recover as r
    assert r._can_drive_gui() is (sys.platform == 'win32')


def test_gui_driver_requires_script_and_desktop(tmp_path, monkeypatch):
    import browser_recover as r
    monkeypatch.setattr(r, 'driver_script', lambda: None)
    assert r._run_gui_load('id', str(tmp_path)) == (False, 'driver_unavailable')
    monkeypatch.setattr(r, 'driver_script', lambda: tmp_path / 'driver.ps1')
    monkeypatch.setattr(r, '_can_drive_gui', lambda: False)
    assert r._run_gui_load('id', str(tmp_path)) == (False, 'driver_unavailable')


def test_gui_driver_maps_subprocess_outcomes(tmp_path, monkeypatch):
    import browser_recover as r
    monkeypatch.setattr(r, 'driver_script', lambda: tmp_path / 'driver.ps1')
    monkeypatch.setattr(r, '_can_drive_gui', lambda: True)
    monkeypatch.setattr(r.subprocess, 'run', lambda *a, **k: _Proc(0, 'LOADED'))
    assert r._run_gui_load('id', str(tmp_path)) == (True, 'loaded')
    monkeypatch.setattr(r.subprocess, 'run', lambda *a, **k: _Proc(0, 'PRESENT-HEALTHY'))
    assert r._run_gui_load('id', str(tmp_path)) == (True, 'loaded')
    monkeypatch.setattr(r.subprocess, 'run', lambda *a, **k: _Proc(1, 'ABORT-USER-ACTIVE'))
    assert r._run_gui_load('id', str(tmp_path)) == (False, 'aborted_user_active')
    monkeypatch.setattr(r.subprocess, 'run', lambda *a, **k: _Proc(1, 'no window found'))
    assert r._run_gui_load('id', str(tmp_path)) == (False, 'driver_failed')

    def boom(*a, **k):
        raise OSError('powershell unavailable')

    monkeypatch.setattr(r.subprocess, 'run', boom)
    assert r._run_gui_load('id', str(tmp_path)) == (False, 'driver_error')


def test_gui_driver_failure_is_returned_and_recorded(tmp_path, monkeypatch):
    import browser_recover as r
    import claude_browser
    monkeypatch.setattr(r, 'app_dir', lambda: tmp_path)
    monkeypatch.setattr(claude_browser, 'diagnose',
                        lambda *a, **k: diag(extension={'present': False, 'disabled': False, 'profiles': []}))
    monkeypatch.setattr(r, 'idle_ms', lambda: 60000.0)
    monkeypatch.setattr(r, '_can_drive_gui', lambda: True)
    monkeypatch.setattr(r, '_run_gui_load', lambda *a: (False, 'driver_failed'))
    out = r.maybe_auto_repair(now=7000.0)
    assert out == {'acted': False, 'reason': 'driver_failed', 'class': 'extension_missing'}
    assert (tmp_path / r.ATTEMPT_NAME).exists()  # recorded, so the driver cannot loop


def test_host_register_paths(tmp_path, monkeypatch):
    import browser_recover as r
    import claude_browser
    ran = []
    monkeypatch.setattr(r.subprocess, 'run', lambda *a, **k: ran.append(a) or _Proc(0, ''))
    monkeypatch.setattr(claude_browser, 'host_exe', lambda: tmp_path / 'absent.exe')
    assert r._run_host_register('abcdef') is False
    assert ran == []  # a missing executable is never spawned
    exe = tmp_path / 'usage-monitor-browser-host.exe'
    exe.write_bytes(b'stub')
    monkeypatch.setattr(claude_browser, 'host_exe', lambda: exe)
    assert r._run_host_register('abcdef') is True
    assert ran and ran[0][0][0] == str(exe) and ran[0][0][1:3] == ['--register', 'abcdef']
    monkeypatch.setattr(r.subprocess, 'run', lambda *a, **k: _Proc(1, ''))
    assert r._run_host_register('abcdef') is False

    def boom(*a, **k):
        raise OSError('spawn failed')

    monkeypatch.setattr(r.subprocess, 'run', boom)
    assert r._run_host_register('abcdef') is False


def test_host_repair_failure_is_reported(tmp_path, monkeypatch):
    import browser_recover as r
    import claude_browser
    monkeypatch.setattr(r, 'app_dir', lambda: tmp_path)
    monkeypatch.setattr(claude_browser, 'diagnose', lambda *a, **k: diag(manifest_exists=False))
    monkeypatch.setattr(claude_browser, 'extension_id', lambda: 'abcdefghijklmnop')
    monkeypatch.setattr(r, '_run_host_register', lambda eid: False)
    r.mark_approved()
    out = r.maybe_auto_repair(now=9000.0)
    assert out == {'acted': False, 'reason': 'register_failed', 'class': 'host_missing'}
    assert (tmp_path / r.ATTEMPT_NAME).exists()

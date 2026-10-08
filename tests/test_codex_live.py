"""Official app-server quota integration and stale-data regressions."""
import json
import subprocess
from pathlib import Path

import pytest

import monitor as m


def response(used=19):
    return {"rateLimits": {"limitId": "codex", "planType": "plus",
            "primary": {"usedPercent": used, "windowDurationMins": 300, "resetsAt": 2999999999},
            "secondary": {"usedPercent": 20, "windowDurationMins": 10080, "resetsAt": 2999999999}}}


def test_live_quota_overrides_local_history(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "_same_home", lambda home: True)
    monkeypatch.setattr(m, "fetch_codex_usage", lambda home: {
        "status": "ok", "rate_limits": m.codex_rate_limits(response())})
    out = m.scan_codex(tmp_path)
    assert out["has_rate"] is True
    assert out["rate_source"] == "official_app_server"
    assert out["rate_limits"]["primary"]["used_percent"] == 19


def test_custom_home_never_starts_codex(tmp_path, monkeypatch):
    def unexpected(home):
        raise AssertionError("Synthetic HOME must not access real account")
    monkeypatch.setattr(m, "fetch_codex_usage", unexpected)
    assert m.scan_codex(tmp_path)["has_rate"] is False


def test_live_failure_does_not_present_history_as_current(tmp_path, monkeypatch):
    d = tmp_path / ".codex" / "sessions"
    d.mkdir(parents=True)
    (d / "old.jsonl").write_text(json.dumps({"timestamp": "2026-10-08T01:49:06Z",
        "payload": {"rate_limits": {"primary": {"used_percent": 31, "resets_at": 2999999999}}}}))
    monkeypatch.setattr(m, "_same_home", lambda home: True)
    monkeypatch.setattr(m, "fetch_codex_usage", lambda home: {"status": "error", "detail": "取得失敗"})
    out = m.scan_codex(tmp_path)
    assert out["has_rate"] is False
    assert out["usage_status"] == "error"
    assert out["rate_limits"]["primary"]["used_percent"] == 31


def test_expired_codex_is_unknown_not_full():
    original = {"has_rate": True, "rate_limits": {"primary": {"used_percent": 31, "resets_at": 1}}}
    out, _ = m.normalize_snapshot(original, {})
    assert out["has_rate"] is False
    assert out["rate_limits"]["primary"]["used_percent"] == 31
    assert out["usage_status"] == "stale"
    assert original["has_rate"] is True


@pytest.mark.parametrize("used", [None, "bad", float("nan"), -1, 101, True])
def test_invalid_quota_rejected(used):
    with pytest.raises(ValueError):
        m.codex_rate_limits(response(used))


def test_named_codex_bucket_preferred():
    data = response(90)
    data["rateLimitsByLimitId"] = {"codex": response(19)["rateLimits"]}
    assert m.codex_rate_limits(data)["primary"]["used_percent"] == 19


def test_official_binary_discovery(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    for version in ("0.9.0", "0.157.1"):
        p = tmp_path / ".codex/packages/standalone/releases" / (version + "-x86_64-pc-windows-msvc") / "bin/codex.exe"
        p.parent.mkdir(parents=True)
        p.touch()
    assert "0.157.1" in str(m.codex_executable(tmp_path))


def test_protocol_waits_for_initialize_and_cleans_up(tmp_path, monkeypatch):
    import io
    class FakeInput(io.StringIO):
        def flush(self):
            rows = self.getvalue().splitlines()
            if json.loads(rows[-1]).get("id") == 2:
                assert json.loads(rows[1])["method"] == "initialized"
    class FakeProcess:
        stdin = FakeInput()
        stdout = io.StringIO(json.dumps({"id": 1, "result": {}}) + "\n" +
                             json.dumps({"method": "notification"}) + "\n" +
                             json.dumps({"id": 2, "result": response()}) + "\n")
        killed = waited = False
        def kill(self): self.killed = True
        def wait(self, **kw): self.waited = True
    proc = FakeProcess()
    monkeypatch.setattr(m, "codex_executable", lambda home: Path("codex.exe"))
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: proc)
    assert m.fetch_codex_usage(tmp_path)["rate_limits"]["primary"]["used_percent"] == 19
    assert proc.killed and proc.waited


def test_timeout_kills_official_process(tmp_path, monkeypatch):
    import io
    class FakeProcess:
        stdin = io.StringIO()
        stdout = io.StringIO()
        killed = waited = False
        def kill(self): self.killed = True
        def wait(self, **kwargs): self.waited = True
    proc = FakeProcess()
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: proc)
    with pytest.raises(TimeoutError):
        m._codex_rpc(Path("codex.exe"), tmp_path, timeout=0)
    assert proc.killed and proc.waited


def test_home_override_applies_to_discovery(tmp_path, monkeypatch):
    root = tmp_path / "custom"
    exe = root / "packages/standalone/releases/0.157.1/bin/codex.exe"
    exe.parent.mkdir(parents=True)
    exe.touch()
    monkeypatch.setenv("CODEX_HOME", str(root))
    assert m.codex_executable(tmp_path) == exe


def test_missing_binary_actionable(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "codex_executable", lambda home: None)
    assert m.fetch_codex_usage(tmp_path)["status"] == "missing_cli"


def test_protocol_errors_do_not_leak_server_message(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "codex_executable", lambda home: Path("codex.exe"))
    monkeypatch.setattr(m, "_codex_rpc", lambda *a: (_ for _ in ()).throw(RuntimeError("secret")))
    out = m.fetch_codex_usage(tmp_path)
    assert out["status"] == "error"
    assert "secret" not in json.dumps(out)

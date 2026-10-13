"""Idle-gated, loop-safe auto recovery for the Claude browser linkage.

Stdlib only. This module never reads credentials, cookies, or page content.
It classifies linkage failures (host vs extension vs stale observation) and
repairs only what is safe without touching the user's Chrome UI:

- Native host re-registration runs automatically, but only when the user has
  previously approved the linkage (approval marker) and a cooldown has passed.
- Extension (re)loading always needs chrome://extensions interaction, so it is
  never driven from here. When the user is active (or activity is unknown),
  even the diagnosis stays read-only and the GUI shows manual steps instead.
- Every decision is appended to a local log with states only, never payloads.
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

IDLE_THRESHOLD_MIN = 10
COOLDOWN_HOURS = 24
APPROVAL_NAME = ".browser-link-approved"
ATTEMPT_NAME = ".browser-recovery-attempt"
LOG_NAME = "browser-recovery.log"


def app_dir() -> Path:
    import os

    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "usage-monitor"


def idle_ms() -> float | None:
    """Milliseconds since last input. None when unavailable."""
    try:
        import ctypes

        class _LI(ctypes.Structure):
            _fields_ = [("size", ctypes.c_uint), ("time", ctypes.c_uint)]

        info = _LI(ctypes.sizeof(_LI), 0)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            return None
        return float((ctypes.windll.kernel32.GetTickCount() - info.time) & 0xFFFFFFFF)
    except Exception:
        return None


def user_active(threshold_min: float = IDLE_THRESHOLD_MIN) -> bool | None:
    """True when input was seen recently. None when it cannot be measured.

    Unknown is treated as active by callers: never drive UI blindly.
    """
    idle = idle_ms()
    if idle is None:
        return None
    return idle < threshold_min * 60 * 1000


def log_event(action: str, detail: str = "") -> None:
    """Append a state-only line. Callers must not pass payloads or secrets."""
    try:
        target = app_dir() / LOG_NAME
        target.parent.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
        line = f"{stamp} {action}" + (f" {detail}" if detail else "") + "\n"
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(line)
    except OSError:
        pass


def approval_given() -> bool:
    return (app_dir() / APPROVAL_NAME).exists()


def mark_approved() -> None:
    try:
        target = app_dir() / APPROVAL_NAME
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("browser-linkage-approved\n", encoding="utf-8")
    except OSError:
        pass


def _last_attempt(now: float) -> float | None:  # noqa: ARG001 - signature kept for symmetry
    try:
        return float((app_dir() / ATTEMPT_NAME).read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _record_attempt(now: float) -> None:
    try:
        target = app_dir() / ATTEMPT_NAME
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(now), encoding="utf-8")
    except OSError:
        pass


def classify(diagnosis: dict) -> str:
    """Map a claude_browser.diagnose() result to one failure class."""
    if not isinstance(diagnosis, dict):
        return "unknown"
    ext = diagnosis.get("extension") or {}
    if ext.get("present") is False:
        return "extension_missing"
    if ext.get("disabled"):
        return "extension_disabled"
    if not diagnosis.get("manifest_exists") or not diagnosis.get("manifest_origin_ok"):
        return "host_missing"
    if diagnosis.get("registry_ok") is False:
        return "host_missing"
    age = diagnosis.get("age_hours")
    try:
        if age is not None and float(age) >= 1:
            return "observation_stale"
    except (TypeError, ValueError):
        pass
    return "healthy"


def _run_host_register(extension_id: str) -> bool:
    import claude_browser

    exe = claude_browser.host_exe()
    if not exe.exists():
        return False
    try:
        proc = subprocess.run(
            [str(exe), "--register", extension_id], capture_output=True,
            text=True, timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return proc.returncode == 0
    except (OSError, ValueError, subprocess.SubprocessError):
        return False


def maybe_auto_repair(now: float | None = None) -> dict:
    """One bounded repair step. Never raises. Never drives Chrome UI."""
    import claude_browser

    now = time.time() if now is None else now
    try:
        diagnosis = claude_browser.diagnose()
    except Exception:
        return {"acted": False, "reason": "diagnose_failed", "class": "unknown"}
    kind = classify(diagnosis)
    if kind == "healthy":
        return {"acted": False, "reason": "healthy", "class": kind}
    last = _last_attempt(now)
    if last is not None and now - last < COOLDOWN_HOURS * 3600:
        return {"acted": False, "reason": "cooldown", "class": kind}
    if kind == "host_missing":
        if not approval_given():
            log_event("repair_skipped", "host_missing/no_approval")
            return {"acted": False, "reason": "no_approval", "class": kind}
        ok = _run_host_register(diagnosis.get("extension_id") or claude_browser.extension_id())
        _record_attempt(now)
        log_event("host_reregister", "ok" if ok else "failed")
        return {"acted": ok, "reason": "host_reregistered" if ok else "register_failed", "class": kind}
    # Extension states need chrome://extensions interaction, which this process
    # must not drive while the user may be active. Record and surface instead.
    active = user_active()
    if active is not False:
        log_event("repair_deferred", f"{kind}/user_active_or_unknown")
        return {"acted": False, "reason": "user_active", "class": kind}
    log_event("repair_deferred", f"{kind}/needs_manual_load")
    return {"acted": False, "reason": "needs_manual_load", "class": kind}

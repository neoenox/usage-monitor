#!/usr/bin/env python3
"""通知閾値などのローカル設定 (JSON, stdlib only)。"""
from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULTS = {"warn_at": 20.0, "crit_at": 10.0}


def path() -> Path:
    d = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "usage-monitor"
    d.mkdir(parents=True, exist_ok=True)
    return d / "settings.json"


def load() -> dict:
    vals = dict(DEFAULTS)
    try:
        raw = json.loads(path().read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            for k in DEFAULTS:
                vals[k] = float(raw.get(k, vals[k]))
    except Exception:
        pass
    err = validate(vals["warn_at"], vals["crit_at"])
    return dict(DEFAULTS) if err else vals


def save(warn_at: float, crit_at: float) -> str | None:
    """成功時None、失敗時エラーメッセージ。"""
    err = validate(warn_at, crit_at)
    if err:
        return err
    try:
        path().write_text(json.dumps({"warn_at": warn_at, "crit_at": crit_at},
                                      ensure_ascii=False, indent=2),
                          encoding="utf-8")
    except Exception as e:
        return f"保存失敗: {e}"
    return None


def validate(warn_at, crit_at) -> str | None:
    try:
        w, c = float(warn_at), float(crit_at)
    except (TypeError, ValueError):
        return "数値を入力してください"
    if not (0 < c < w <= 100):
        return "0 < 緊急 < 警告 ≦ 100 にしてください"
    return None

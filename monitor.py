#!/usr/bin/env python3
"""codex + claude usage snapshot monitor (stdlib only).

Codex:  ~/.codex/sessions/**/*.jsonl の token_count イベントを集計
  - トークン: ファイル毎の最終 total_token_usage を合算 (input/output/cached)
  - レート制限: 最新タイムスタンプの rate_limits を採用 (primary 5h / secondary 週次)
Claude: ~/.claude/projects/**/*.jsonl の assistant message.usage を合算
  - 履歴が無ければ 0 + files=0 と明示 (現環境で確認済みの制約)
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

CLAUDE_USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
CLAUDE_USAGE_BETA = "oauth-2025-04-20"
CLAUDE_TOKEN_URL = "https://console.anthropic.com/v1/oauth/token"
CLAUDE_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"  # Claude Code public OAuth client
CLAUDE_CRED_TARGET = "Claude Code-credentials"  # OS credential store service name


def fmt_num(n: int) -> str:
    return f"{n:,}"


def iso_to_epoch(s: str | None) -> int | None:
    if not s:
        return None
    try:
        return int(datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp())
    except Exception:
        return None


def fmt_countdown(target) -> str:
    """リセット時刻までの残り時間。epoch数値 or ISO文字列を受け付ける。"""
    import time

    if isinstance(target, str):
        target = iso_to_epoch(target)
    if not target:
        return "-"
    try:
        diff = int(float(target) - time.time())
    except (TypeError, ValueError):
        return "-"
    if diff <= 0:
        return "まもなく"
    d, h, m = diff // 86400, (diff % 86400) // 3600, (diff % 3600) // 60
    if d:
        return f"あと{d}日{h}時間{m}分"
    return f"あと{h}時間{m}分" if h else f"あと{m}分"


def project_hit(used: float | None, window_min: int, reset_epoch: int | None,
                 hist: list[tuple[int, float]] | tuple = ()) -> int | None:
    """このペースで100%に達するepochを予測。窓内に収まる場合のみ返す。

    履歴(同一窓内の2点以上・10分以上の幅)があれば傾きを使用、
    なければ窓開始→現在の線形で推定。buryな利用のため目安。
    """
    import time

    now = int(time.time())
    if not reset_epoch or window_min <= 0:
        return None
    try:
        reset_epoch = int(float(reset_epoch))
    except (TypeError, ValueError):
        return None
    start = reset_epoch - window_min * 60
    pts = sorted((int(t), float(u)) for t, u in hist if int(t) >= start)
    if len(pts) >= 2 and pts[-1][0] - pts[0][0] >= 600 and pts[-1][1] > pts[0][1]:
        dt = pts[-1][0] - pts[0][0]
        du = pts[-1][1] - pts[0][1]
        t_hit = pts[-1][0] + (100 - pts[-1][1]) / du * dt
    else:
        if used is None:
            return None
        try:
            used = float(used)
        except (TypeError, ValueError):
            return None
        el = now - start
        if el <= 60 or used <= 0:
            return None
        t_hit = start + 100 / used * el
    return int(t_hit) if t_hit < reset_epoch else None


def pace_label(used: float | None, window_min: int, reset_epoch: int | None,
               hist: list[tuple[int, float]] | tuple = ()) -> str:
    hit = project_hit(used, window_min, reset_epoch, hist)
    if hit is None:
        return "このペースならセーフ"
    return f"このままだと{fmt_ts(hit)}頃枯渇"


def fmt_ts_iso(s: str | None) -> str:
    if not s:
        return "-"
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone()
        return dt.strftime("%m-%d %H:%M")
    except Exception:
        return "-"


def fmt_ts(epoch: int | float | None) -> str:
    if not epoch:
        return "-"
    try:
        dt = datetime.fromtimestamp(float(epoch), tz=timezone.utc).astimezone()
        return dt.strftime("%m-%d %H:%M")
    except Exception:
        return "-"


def scan_codex(home: Path) -> dict:
    base = home / ".codex" / "sessions"
    files = sorted(base.rglob("*.jsonl")) if base.exists() else []
    total_in = total_out = total_cached = 0
    sessions_with_tokens = 0
    # レート制限は「mtime最新ファイルの最終token_countイベント」を採用
    # (コミュニティツールと同方式。timestamp文字列のmax比較は未来日付混入に弱い)
    newest_with_tokens = None
    for f in files:
        last_usage = None
        try:
            with open(f, encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    if "token_count" not in line and "rate_limits" not in line:
                        continue
                    try:
                        d = json.loads(line)
                    except Exception:
                        continue
                    payload = d.get("payload", {}) if isinstance(d, dict) else {}
                    info = payload.get("info", {}) if isinstance(payload, dict) else {}
                    tu = info.get("total_token_usage") or payload.get("total_token_usage")
                    if isinstance(tu, dict) and "input_tokens" in tu:
                        last_usage = tu
                        newest_with_tokens = (f, tu)
        except Exception:
            continue
        if last_usage:
            sessions_with_tokens += 1
            total_in += int(last_usage.get("input_tokens") or 0)
            total_out += int(last_usage.get("output_tokens") or 0)
            total_cached += int(last_usage.get("cached_input_tokens") or 0)
    # mtime降順で最初にtoken_countを持つファイルの最終イベントからrate_limits取得
    latest_rl = None
    latest_rl_file = ""
    context: dict = {}
    for f in sorted(files, key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            with open(f, encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    if "token_count" not in line and "rate_limits" not in line:
                        continue
                    try:
                        d = json.loads(line)
                    except Exception:
                        continue
                    payload = d.get("payload", {}) if isinstance(d, dict) else {}
                    if "rate_limits" in line:
                        rl = payload.get("rate_limits", {})
                        if isinstance(rl, dict) and "primary" in rl:
                            latest_rl = rl
                    if "token_count" in line:
                        info = payload.get("info", {}) if isinstance(payload, dict) else {}
                        last = info.get("last_token_usage") or {}
                        win = info.get("model_context_window") or 0
                        try:
                            ctx_in = int(last.get("input_tokens") or 0)
                            win = int(win)
                        except (TypeError, ValueError, AttributeError):
                            continue
                        if win > 0:
                            context = {"input": ctx_in, "window": win,
                                       "pct": round(ctx_in / win * 100, 1)}
            if latest_rl is not None:
                latest_rl_file = f.name
                break
        except Exception:
            continue
    return {
        "files": len(files),
        "sessions_with_tokens": sessions_with_tokens,
        "input": total_in,
        "output": total_out,
        "cached": total_cached,
        "total": total_in + total_out,
        "rate_limits": latest_rl or {},
        "rate_source": latest_rl_file,
        "context": context,
    }


def scan_claude(home: Path) -> dict:
    base = home / ".claude" / "projects"
    files = sorted(base.rglob("*.jsonl")) if base.exists() else []
    inp = out = cache_c = cache_r = 0
    msgs = 0
    for f in files:
        try:
            with open(f, encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    if '"usage"' not in line:
                        continue
                    try:
                        d = json.loads(line)
                    except Exception:
                        continue
                    u = (d.get("message") or {}).get("usage") if isinstance(d, dict) else None
                    if not isinstance(u, dict):
                        continue
                    msgs += 1
                    inp += int(u.get("input_tokens") or 0)
                    out += int(u.get("output_tokens") or 0)
                    cache_c += int(u.get("cache_creation_input_tokens") or 0)
                    cache_r += int(u.get("cache_read_input_tokens") or 0)
        except Exception:
            continue
    oauth = fetch_claude_oauth(home)
    return {
        "files": len(files),
        "messages": msgs,
        "input": inp,
        "output": out,
        "cache_creation": cache_c,
        "cache_read": cache_r,
        "total": inp + out,
        "oauth": oauth,
    }


def claude_token(home: Path) -> str:
    """Resolve Claude OAuth access token (memory only, never persisted).

    Order: env CLAUDE_CODE_OAUTH_TOKEN / ~/.claude_oauth_token file /
    ~/.claude/.credentials.json (written by `claude auth login`) /
    OS credential store entry (with refresh when expired).
    """
    tok = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "").strip()
    if tok:
        return tok
    try:
        p = home / ".claude_oauth_token"
        if p.exists():
            tok = p.read_text(encoding="utf-8", errors="ignore").strip()
            if tok:
                return tok
    except Exception:
        pass
    try:
        p = home / ".claude" / ".credentials.json"
        if p.exists():
            creds = json.loads(p.read_text(encoding="utf-8", errors="ignore"))
            tok = _resolve_oauth_access(creds.get("claudeAiOauth") or {})
            if tok:
                return tok
    except Exception:
        pass
    return claude_token_from_os_store()


def _resolve_oauth_access(oauth: dict) -> str:
    """Return a live accessToken from a claudeAiOauth dict, refreshing if expired."""
    import time

    access = str(oauth.get("accessToken") or "")
    try:
        expired = float(oauth.get("expiresAt") or 0) / 1000 < time.time() + 60
    except (TypeError, ValueError):
        expired = True
    if access and not expired:
        return access
    refresh = str(oauth.get("refreshToken") or "")
    if not refresh:
        return access  # try anyway; API will tell
    try:
        body = json.dumps(
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh,
                "client_id": CLAUDE_CLIENT_ID,
            }
        ).encode()
        req = urllib.request.Request(
            CLAUDE_TOKEN_URL, data=body, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as res:
            data = json.loads(res.read().decode("utf-8", "ignore"))
        return str(data.get("access_token") or "")
    except Exception:
        return ""


def claude_token_from_os_store() -> str:
    """Read OAuth creds Claude Code stored in the OS credential store.

    Windows: Credential Manager target "Claude Code-credentials" (keytar).
    Returns a live accessToken, refreshing it when expired. "" when absent.
    """
    import time

    raw = _read_credential_store(CLAUDE_CRED_TARGET)
    if not raw:
        return ""
    try:
        oauth = json.loads(raw).get("claudeAiOauth") or {}
    except Exception:
        return ""
    return _resolve_oauth_access(oauth)


def _read_credential_store(target: str) -> str:
    """Windows Credential Manager generic-credential password via ctypes."""
    import ctypes
    from ctypes import wintypes

    class CREDENTIAL(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", wintypes.FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", wintypes.LPBYTE),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", wintypes.LPVOID),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

    advapi32 = ctypes.windll.advapi32
    pcred = ctypes.POINTER(CREDENTIAL)()
    if not advapi32.CredReadW(target, 1, 0, ctypes.byref(pcred)):
        return ""
    try:
        size = int(pcred.contents.CredentialBlobSize)
        buf = ctypes.string_at(pcred.contents.CredentialBlob, size)
        return buf.decode("utf-16-le", errors="ignore").rstrip("\x00")
    except Exception:
        return ""
    finally:
        advapi32.CredFree(pcred)


def fetch_claude_oauth(home: Path) -> dict:
    """GET /api/oauth/usage (same endpoint Claude Code /usage uses).

    Returns {"status": "ok", "five_hour": {...}, "seven_day": {...}}
    or {"status": "missing_token" | "error", "detail": ...}.
    Token: `claude setup-token` once, then env CLAUDE_CODE_OAUTH_TOKEN
    or write it to ~/.claude_oauth_token.
    """
    tok = claude_token(home)
    if not tok:
        return {"status": "missing_token"}
    try:
        req = urllib.request.Request(
            CLAUDE_USAGE_URL,
            headers={
                "Authorization": f"Bearer {tok}",
                "anthropic-beta": CLAUDE_USAGE_BETA,
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as res:
            data = json.loads(res.read().decode("utf-8", "ignore"))
        if not isinstance(data, dict):
            return {"status": "error", "detail": "unexpected response"}
        return {
            "status": "ok",
            "five_hour": data.get("five_hour") or {},
            "seven_day": data.get("seven_day") or {},
            "seven_day_opus": data.get("seven_day_opus") or {},
            "seven_day_sonnet": data.get("seven_day_sonnet") or {},
        }
    except Exception as e:
        return {"status": "error", "detail": f"{type(e).__name__}: {e}"}


def main() -> int:
    ap = argparse.ArgumentParser(description="codex + claude usage snapshot")
    ap.add_argument("--json", action="store_true", help="JSON出力")
    ap.add_argument("--home", default=os.path.expanduser("~"), help="ホームディレクトリ")
    args = ap.parse_args()
    home = Path(args.home)

    codex = scan_codex(home)
    claude = scan_claude(home)

    if args.json:
        print(json.dumps({"codex": codex, "claude": claude}, ensure_ascii=False, indent=2))
        return 0

    rl = codex.get("rate_limits", {}) or {}
    pri = rl.get("primary", {}) or {}
    sec = rl.get("secondary", {}) or {}
    plan = rl.get("plan_type", "-")

    print("=== Usage Monitor (snapshot) ===")
    print(f"[Codex] sessions: {codex['files']} (with tokens {codex['sessions_with_tokens']}) plan={plan}")
    print(f"  input   : {fmt_num(codex['input'])}")
    print(f"  output  : {fmt_num(codex['output'])}")
    print(f"  cached  : {fmt_num(codex['cached'])}")
    print(f"  total   : {fmt_num(codex['total'])}")
    if pri or sec:
        # Codex UI shows REMAINING %. Show both to avoid confusion.
        p_used = float(pri.get("used_percent") or 0)
        s_used = float(sec.get("used_percent") or 0)
        try:
            import history as _h
            h5, hw = _h.recent("codex_5h"), _h.recent("codex_wk")
        except Exception:
            h5, hw = [], []
        print(f"  5h      : {100 - p_used:.0f}% left (used {p_used:.0f}%) "
              f"reset={fmt_ts(pri.get('resets_at'))} ({fmt_countdown(pri.get('resets_at'))}) "
              f"[{pace_label(p_used, 300, pri.get('resets_at'), h5)}]")
        print(f"  weekly  : {100 - s_used:.0f}% left (used {s_used:.0f}%) "
              f"reset={fmt_ts(sec.get('resets_at'))} ({fmt_countdown(sec.get('resets_at'))}) "
              f"[{pace_label(s_used, 10080, sec.get('resets_at'), hw)}]")
        ctx = codex.get("context", {}) or {}
        if ctx:
            print(f"  context : {ctx['pct']}% ({fmt_num(ctx['input'])}/{fmt_num(ctx['window'])})")
    else:
        print("  rate-limit: no history")
    print(f"[Claude] transcripts: {claude['files']} messages: {claude['messages']} (src: ~/.claude/projects)")
    if claude["files"] <= 1:
        print("  NOTE: local history was auto-cleaned; real usage is NOT reflected")
    print(f"  input   : {fmt_num(claude['input'])}")
    print(f"  output  : {fmt_num(claude['output'])}")
    print(f"  cache_create: {fmt_num(claude['cache_creation'])} cache_read: {fmt_num(claude['cache_read'])}")
    print(f"  total   : {fmt_num(claude['total'])}")
    oauth = claude.get("oauth", {}) or {}
    if oauth.get("status") == "ok":
        try:
            import history as _h2
            ch5, chw = _h2.recent("claude_5h"), _h2.recent("claude_wk")
        except Exception:
            ch5, chw = [], []
        win_min = {"five_hour": 300, "seven_day": 10080}
        hist_of = {"five_hour": ch5, "seven_day": chw}
        for label, key in (("5h", "five_hour"), ("weekly", "seven_day"),
                           ("wk-opus", "seven_day_opus"), ("wk-sonnet", "seven_day_sonnet")):
            w = oauth.get(key, {}) or {}
            u = w.get("utilization")
            if u is None:
                continue
            try:
                left = 100 - float(u)
                pace = pace_label(float(u), win_min.get(key, 0),
                                  iso_to_epoch(w.get("resets_at")), hist_of.get(key, []))
                print(f"  {label:<8}: {left:.0f}% left (used {float(u):.0f}%) "
                      f"reset={fmt_ts_iso(w.get('resets_at'))} ({fmt_countdown(w.get('resets_at'))}) [{pace}]")
            except (TypeError, ValueError):
                print(f"  {label:<8}: -")
    elif oauth.get("status") == "missing_token":
        print("  subscription usage: no token. Run `claude setup-token`, then set")
        print("  env CLAUDE_CODE_OAUTH_TOKEN or write token to ~/.claude_oauth_token")
    else:
        print(f"  subscription usage: error ({oauth.get('detail', '?')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

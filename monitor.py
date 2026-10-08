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

__version__ = "0.5.0"

CLAUDE_USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
CLAUDE_USAGE_BETA = "oauth-2025-04-20"
CLAUDE_TOKEN_URL = "https://console.anthropic.com/v1/oauth/token"
CLAUDE_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"  # Claude Code public OAuth client
CLAUDE_CRED_TARGET = "Claude Code-credentials"  # OS credential store service name
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def fmt_num(n: int) -> str:
    return f"{n:,}"

def iso_to_epoch(s: str | None) -> int | None:
    if not s:
        return None
    try:
        return int(datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp())
    except Exception:
        return None


def is_stale(reset) -> bool:
    """リセット時刻を過ぎていたら前窓の古い値として扱う。"""
    import time

    if isinstance(reset, str):
        reset = iso_to_epoch(reset)
    try:
        return bool(reset) and int(float(reset)) < time.time()
    except (TypeError, ValueError):
        return False


def normalize_snapshot(codex: dict, claude: dict) -> tuple[dict, dict]:
    """窓終了後の古い値を新窓(使用0%)に正規化。起動直後や朝一番の表示崩れ防止。
    元dictは変更しない。new_window_* フラグを付与。"""
    import copy

    codex, claude = copy.deepcopy(codex), copy.deepcopy(claude)
    rl = codex.get("rate_limits", {}) or {}
    for key, flag in (("primary", "new_window_5h"), ("secondary", "new_window_wk")):
        w = rl.get(key, {}) or {}
        if w.get("resets_at") and is_stale(w.get("resets_at")):
            w["used_percent"] = 0.0
            codex[flag] = True
    oauth = claude.get("oauth", {}) or {}
    if oauth.get("status") == "ok":
        for key, flag in (("five_hour", "new_window_5h"), ("seven_day", "new_window_wk")):
            w = oauth.get(key, {}) or {}
            if w.get("resets_at") and is_stale(w.get("resets_at")):
                w["utilization"] = 0.0
                claude[flag] = True
    return codex, claude


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
               hist: list[tuple[int, float]] | tuple = (),
               show_date: bool = True) -> str:
    hit = project_hit(used, window_min, reset_epoch, hist)
    if hit is None:
        return "このペースならセーフ"
    when = fmt_ts(hit) if show_date else datetime.fromtimestamp(hit).astimezone().strftime("%H:%M")
    return f"このままだと{when}頃枯渇"


def week_pace(used: float | None, window_min: int, reset_epoch: int | None) -> str:
    """週窓のペース判定: 経過%に対する使用%。over/under/on pace。
    短窓(5h)はブレが大きいため週窓用。"""
    import time

    try:
        used = float(used) if used is not None else None
        reset_epoch = int(float(reset_epoch))
    except (TypeError, ValueError):
        return "-"
    if used is None or window_min <= 0:
        return "-"
    now = int(time.time())
    elapsed = now - (reset_epoch - window_min * 60)
    if elapsed <= 0:
        return "-"
    expected = elapsed / (window_min * 60) * 100
    if used >= expected * 1.1:
        return f"over pace (経過{expected:.0f}%に対し使用{used:.0f}%)"
    if used <= expected * 0.9:
        return f"under pace (経過{expected:.0f}%に対し使用{used:.0f}%)"
    return f"on pace (経過{expected:.0f}%/使用{used:.0f}%)"


def week_budget(used: float | None, reset_epoch: int | None) -> str:
    """週窓のburn-down予算: 残量を残り日数で割った「1日あたり使える%」。
    短期ペース(枯渇予測)の代わりに週窓用として使う。"""
    import time

    try:
        used = float(used) if used is not None else None
        reset_epoch = int(float(reset_epoch))
    except (TypeError, ValueError):
        return "-"
    if used is None:
        return "-"
    left = 100.0 - used
    if left <= 0:
        return "予算なし(上限到達)"
    now = int(time.time())
    remaining = reset_epoch - now
    if remaining <= 0:
        return "まもなくリセット"
    if remaining < 3600:
        return f"残り{left:.0f}%をキープ"
    days = remaining / 86400
    if days < 1:
        return f"残り{left:.0f}%をキープ"
    return f"1日{left / days:.0f}%まで"


def week_status(used: float | None, reset_epoch: int | None) -> str:
    """週窓の一本化表示: week_pace + 日次予算。"""
    return f"{week_pace(used, 10080, reset_epoch)}・{week_budget(used, reset_epoch)}"


def day_bounds(days_ago: int = 1) -> tuple[int, int]:
    """days_ago日前のローカル日境界 (start, end) をepoch秒で返す。"""
    import time

    lt = time.localtime(time.time())
    day = datetime(lt.tm_year, lt.tm_mon, lt.tm_mday) - timedelta(days=days_ago)
    next_day = day + timedelta(days=1)
    # Resolve DST independently at each midnight, not at the current time.
    start = int(time.mktime(day.timetuple()))
    end = int(time.mktime(next_day.timetuple()))
    return start, end


def daily_max_used(points: list[tuple[int, float]], start: int, end: int) -> float | None:
    """指定範囲の使用%最大値。点がなければNone。"""
    vals = [float(u) for t, u in points if start <= int(t) < end]
    return max(vals) if vals else None


def daily_report_lines(yesterday: dict[str, float | None],
                       week_verdicts: dict[str, str]) -> list[str]:
    """朝バルーン用の3-4行レポートを生成。"""
    names = (("codex_5h", "Codex 5h"), ("codex_wk", "Codex週"),
             ("claude_5h", "Claude 5h"), ("claude_wk", "Claude週"))
    parts = []
    for key, label in names:
        v = yesterday.get(key)
        parts.append(f"{label}最大{v:.0f}%" if v is not None else f"{label}-")
    lines = ["昨日 " + "・".join(parts)]
    for key, label in (("codex_wk", "Codex週"), ("claude_wk", "Claude週")):
        if week_verdicts.get(key):
            lines.append(f"{label}: {week_verdicts[key]}")
    return lines


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
    # レート制限は「全ファイル中の最新token_countイベント」を採用。
    # mtime順では複数セッションが交互追記されると古い値を掴むため、
    # イベントtimestampをepochへ正規化して選ぶ。primaryがdictでない行は除外。
    latest_rl = None
    latest_rl_epoch = None
    latest_rl_file = ""
    for f in files:
        try:
            with open(f, encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    if "rate_limits" not in line:
                        continue
                    try:
                        d = json.loads(line)
                    except Exception:
                        continue
                    payload = d.get("payload", {}) if isinstance(d, dict) else {}
                    rl = payload.get("rate_limits") if isinstance(payload, dict) else None
                    if not isinstance(rl, dict) or not isinstance(rl.get("primary"), dict):
                        continue
                    ts = d.get("timestamp")
                    if not ts:
                        # Keep the legacy fallback if no dated event is available.
                        if latest_rl_epoch is None:
                            latest_rl = rl
                            latest_rl_file = f.name
                        continue
                    ts_epoch = iso_to_epoch(str(ts))
                    if ts_epoch is None:
                        continue
                    if latest_rl_epoch is None or ts_epoch >= latest_rl_epoch:
                        latest_rl_epoch = ts_epoch
                        latest_rl = rl
                        latest_rl_file = f.name
        except Exception:
            continue
    # contextも全ファイル中の最新token_countイベントから取得
    context: dict = {}
    latest_ctx_ts = ""
    for f in files:
        try:
            with open(f, encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    if "token_count" not in line:
                        continue
                    try:
                        d = json.loads(line)
                    except Exception:
                        continue
                    ts = str(d.get("timestamp", ""))
                    if ts < latest_ctx_ts:
                        continue
                    payload = d.get("payload", {}) if isinstance(d, dict) else {}
                    info = payload.get("info", {}) if isinstance(payload, dict) else {}
                    last = info.get("last_token_usage") or {}
                    win = info.get("model_context_window") or 0
                    try:
                        ctx_in = int(last.get("input_tokens") or 0)
                        win = int(win)
                    except (TypeError, ValueError, AttributeError):
                        continue
                    if win > 0:
                        latest_ctx_ts = ts
                        context = {"input": ctx_in, "window": win,
                                   "pct": round(ctx_in / win * 100, 1)}
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
        "has_rate": latest_rl is not None,
        "context": context,
    }


def _same_home(home: Path) -> bool:
    """Return True only when *home* is the process user's real home."""
    try:
        return home.expanduser().resolve() == Path.home().expanduser().resolve()
    except (OSError, RuntimeError):
        return False


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
    # A caller that supplies another HOME is asking for an isolated scan.
    # Do not fall through to this machine's env token or OS credential store.
    oauth = fetch_claude_oauth(home, isolated=not _same_home(home))
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


def claude_token(home: Path, *, isolated: bool = False) -> str:
    """Resolve Claude OAuth access token (memory only, never persisted).

    Order: env CLAUDE_CODE_OAUTH_TOKEN / ~/.claude_oauth_token file /
    ~/.claude/.credentials.json (written by `claude auth login`) /
    OS credential store entry (with refresh when expired).
    期限切れ時は公式CLIに再取得させる (30分クールダウン)。
    """
    if not isolated:
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
    for _ in range(2):  # 初回 + CLI再取得後の再読込
        try:
            p = home / ".claude" / ".credentials.json"
            if p.exists():
                creds = json.loads(p.read_text(encoding="utf-8", errors="ignore"))
                tok = _resolve_oauth_access(creds.get("claudeAiOauth") or {})
                if tok:
                    return tok
                if _cli_refresh_creds(home):
                    continue
                break  # try the OS store even when credentials.json is expired
        except Exception:
            pass
        break
    return "" if isolated else claude_token_from_os_store()


def claude_has_creds(home: Path, *, isolated: bool = False) -> bool:
    try:
        if (home / ".claude" / ".credentials.json").exists():
            return True
    except Exception:
        pass
    try:
        if (home / ".claude_oauth_token").read_text(encoding="utf-8").strip():
            return True
    except (OSError, UnicodeError):
        pass
    if isolated:
        return False
    if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "").strip():
        return True
    try:
        return bool(_read_credential_store(CLAUDE_CRED_TARGET))
    except (OSError, AttributeError):
        return False


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
    return _refresh_oauth(refresh)


def _refresh_oauth(refresh: str) -> str:
    """リフレッシュ1回のみ (リトライループ禁止: エンドポイントが厳格)。"""
    try:
        body = json.dumps(
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh,
                "client_id": CLAUDE_CLIENT_ID,
            }
        ).encode()
        req = urllib.request.Request(
            CLAUDE_TOKEN_URL, data=body,
            headers={"Content-Type": "application/json", "User-Agent": BROWSER_UA,
                     "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as res:
            data = json.loads(res.read().decode("utf-8", "ignore"))
        return str(data.get("access_token") or "")
    except Exception:
        return ""


def _cli_refresh_creds(home: Path) -> bool:
    """公式CLIに極小APIコールを1発投げて資格情報ファイルを更新させる。
    30分クールダウン。成功時True。
    """
    import shutil
    import subprocess
    import time

    if not shutil.which("claude"):
        return False
    try:
        from pathlib import Path as _P

        import os as _os

        mark = _P(_os.environ.get("LOCALAPPDATA", str(home))) / "usage-monitor" / ".cli_refresh"
        if mark.exists() and time.time() - mark.stat().st_mtime < 1800:
            return False
    except Exception:
        pass
    try:
        proc = subprocess.run(
            ["claude", "-p", "ping", "--output-format", "text"],
            capture_output=True, timeout=120,
            cwd=str(home),
        )
        if proc.returncode != 0:
            return False
        try:
            mark.parent.mkdir(parents=True, exist_ok=True)
            mark.write_text("1", encoding="utf-8")
        except Exception:
            pass
        return True
    except Exception:
        return False


def claude_token_from_os_store() -> str:
    """Read OAuth creds Claude Code stored in the OS credential store.

    Windows: Credential Manager target "Claude Code-credentials" (keytar).
    Returns a live accessToken, refreshing it when expired. "" when absent.
    """
    if os.name != "nt":
        return ""
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
    if os.name != "nt":
        return ""
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


def fetch_claude_oauth(home: Path, *, isolated: bool = False) -> dict:
    """GET /api/oauth/usage (same endpoint Claude Code /usage uses).

    Returns {"status": "ok", "five_hour": {...}, "seven_day": {...}}
    or {"status": "missing_token" | "error", "detail": ...}.
    Token: `claude auth login` (auto-read) or env CLAUDE_CODE_OAUTH_TOKEN
    or write it to ~/.claude_oauth_token.
    """
    tok = claude_token(home, isolated=isolated)
    if not tok:
        if claude_has_creds(home, isolated=isolated):
            return {"status": "expired"}
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
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = ap.parse_args()
    home = Path(args.home)

    codex = scan_codex(home)
    claude = scan_claude(home)
    codex, claude = normalize_snapshot(codex, claude)

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
            h5 = _h.recent("codex_5h")
        except Exception:
            h5 = []
        print(f"  5h      : {100 - p_used:.0f}% left (used {p_used:.0f}%) "
              f"reset={fmt_ts(pri.get('resets_at'))} ({fmt_countdown(pri.get('resets_at'))}) "
              f"[{pace_label(p_used, 300, pri.get('resets_at'), h5, False)}]"
              f"{' (new window)' if codex.get('new_window_5h') else ''}")
        print(f"  weekly  : {100 - s_used:.0f}% left (used {s_used:.0f}%) "
              f"reset={fmt_ts(sec.get('resets_at'))} ({fmt_countdown(sec.get('resets_at'))}) "
              f"<{week_status(s_used, sec.get('resets_at'))}>")
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
        try:
            import history as _h2
            ch5 = _h2.recent("claude_5h")
        except Exception:
            ch5 = []
        for label, key in (("5h", "five_hour"), ("weekly", "seven_day"),
                           ("wk-opus", "seven_day_opus"), ("wk-sonnet", "seven_day_sonnet")):
            w = oauth.get(key, {}) or {}
            u = w.get("utilization")
            if u is None:
                continue
            try:
                left = 100 - float(u)
                reset_ep = iso_to_epoch(w.get("resets_at"))
                if key == "five_hour":
                    pace = pace_label(float(u), 300, reset_ep, ch5, False)
                    extra = f"[{pace}]"
                elif key == "seven_day":
                    extra = f"<{week_status(float(u), reset_ep)}>"
                else:
                    extra = f"<{week_status(float(u), reset_ep)}>" if w.get("resets_at") else ""
                print(f"  {label:<8}: {left:.0f}% left (used {float(u):.0f}%) "
                      f"reset={fmt_ts_iso(w.get('resets_at'))} ({fmt_countdown(w.get('resets_at'))}) {extra}")
            except (TypeError, ValueError):
                print(f"  {label:<8}: -")
    elif oauth.get("status") == "missing_token":
        print("  subscription usage: no token. Run `claude auth login` once.")
    elif oauth.get("status") == "expired":
        print("  subscription usage: token expired, auto-refresh failed.")
        print("  Use claude once (or wait); next refresh retries automatically.")
    else:
        print(f"  subscription usage: error ({oauth.get('detail', '?')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


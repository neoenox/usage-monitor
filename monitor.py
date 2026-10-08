#!/usr/bin/env python3
"""codex + claude usage snapshot monitor (stdlib only).

Codex:  公式Codex app-serverからアカウント全体の使用量を取得
  - トークン: sessions/**/*.jsonl の最終 total_token_usage を合算 (input/output/cached)
  - レート制限: account/rateLimits/read (primary 5h / secondary 週次)
  - カスタムHOMEではネットワークに接続せずローカル履歴のみ
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

__version__ = "0.5.2"

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
    """Codexの期限切れ値は不明扱い。Claudeの従来の新窓処理は維持。
    元dictは変更しない。"""
    import copy

    codex, claude = copy.deepcopy(codex), copy.deepcopy(claude)
    rl = codex.get("rate_limits", {}) or {}
    for key, flag in (("primary", "new_window_5h"), ("secondary", "new_window_wk")):
        w = rl.get(key, {}) or {}
        if not codex.get("quota_cached") and w.get("resets_at") and is_stale(w.get("resets_at")):
            codex["has_rate"] = False
            if codex.get("usage_status") in (None, "ok", "local_history"):
                codex["usage_status"] = "stale"
                codex["usage_detail"] = "リセット後の最新データを取得できていません"
    oauth = claude.get("oauth", {}) or {}
    if oauth.get("status") == "ok" and not claude.get("quota_cached"):
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


def _forecast_result(used, window_min, reset_epoch, hist=(), show_date=True) -> tuple[str, int | None]:
    """Explain a forecast only when comparable samples establish a recent rate."""
    import math
    import time

    now = time.time()
    try:
        if any(isinstance(v, bool) for v in (used, reset_epoch, window_min)):
            return "データ不足で予測できません", None
        used, reset_epoch, window_min = float(used), float(reset_epoch), float(window_min)
        if not all(math.isfinite(v) for v in (used, reset_epoch, window_min)) or not 0 <= used <= 100 or window_min <= 0:
            return "データ不足で予測できません", None
    except (TypeError, ValueError):
        return "データ不足で予測できません", None
    if reset_epoch <= now:
        return "リセット後のデータを待っています", None
    if used >= 100:
        return "利用上限に達しています", None
    start = reset_epoch - window_min * 60
    points = []
    try:
        for t, u in hist:
            if any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) for v in (t, u)) or not 0 <= u <= 100:
                return "履歴不足で予測できません", None
            if start <= t <= now:
                points.append((t, u))
        points.sort()
    except (TypeError, ValueError, OverflowError):
        return "履歴不足で予測できません", None
    if len(points) < 2 or points[-1][0] - points[0][0] < 600:
        return "履歴不足で予測できません", None
    if any(b[1] < a[1] for a, b in zip(points, points[1:])) or used < points[-1][1]:
        return "履歴不足で予測できません", None
    # Treat the current snapshot as the newest observation before deciding
    # that usage is flat. This also recovers from historical bogus 0% samples.
    if now > points[-1][0] and used > points[-1][1]:
        points.append((now, used))
    delta = points[-1][1] - points[0][1]
    if delta == 0:
        return "リセットまで持つ見込み", None
    rate = delta / (points[-1][0] - points[0][0])
    # The remaining quota belongs to the current snapshot, so forecast from now.
    hit = now + (100 - used) / rate
    if hit >= reset_epoch:
        return "リセットまで持つ見込み", None
    if hit <= now:
        return "上限に達する見込み（予測時刻を経過）", None
    minutes = max(1, math.ceil((hit - now) / 60))
    days, rest = divmod(minutes, 1440)
    hours, minutes = divmod(rest, 60)
    duration = (f"{days}日" if days else "") + (f"{hours}時間" if hours else "") + (f"{minutes}分" if minutes else "")
    return f"約{duration}後に上限へ達する見込み", int(hit)


def quota_forecast(used, window_min, reset_epoch, hist=(), show_date=True) -> str:
    return _forecast_result(used, window_min, reset_epoch, hist, show_date)[0]


def project_hit(used, window_min, reset_epoch, hist=()) -> int | None:
    """Compatibility interface backed by the shared observed-sample forecast."""
    return _forecast_result(used, window_min, reset_epoch, hist)[1]


def pace_label(used, window_min, reset_epoch, hist=(), show_date=True) -> str:
    return quota_forecast(used, window_min, reset_epoch, hist, show_date)


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


def codex_executable(home: Path) -> Path | None:
    """Find the official binary, including the desktop app's bundled CLI."""
    import re
    import shutil

    root = Path(os.environ.get("CODEX_HOME") or home / ".codex")
    candidates = list(root.glob("packages/*/releases/*/bin/codex.exe"))
    def version(path):
        match = re.search(r"(\d+)\.(\d+)\.(\d+)", str(path))
        return tuple(map(int, match.groups())) if match else (0, 0, 0)
    if candidates:
        return max(candidates, key=version)
    cli = shutil.which("codex.exe") or shutil.which("codex")
    # Windows npm launchers require a shell. Locate their native binary instead.
    if cli and Path(cli).suffix.lower() not in (".cmd", ".ps1", ".bat"):
        return Path(cli)
    npm = home / "AppData/Roaming/npm/node_modules/@openai"
    candidates = list(npm.glob("codex*/**/codex.exe"))
    return max(candidates, key=version) if candidates else None


def codex_rate_limits(data: dict) -> dict:
    """Validate and translate the official account/rateLimits/read response."""
    import math

    buckets = data.get("rateLimitsByLimitId") or {}
    rl = buckets.get("codex") or data.get("rateLimits")
    if not isinstance(rl, dict) or rl.get("limitId") not in (None, "codex"):
        raise ValueError("Missing Codex quota")
    result = {"plan_type": rl.get("planType", "-"), "limit_id": "codex"}
    for key in ("primary", "secondary"):
        w = rl.get(key)
        if not isinstance(w, dict):
            raise ValueError("Missing quota window")
        used = w.get("usedPercent")
        if isinstance(used, bool) or not isinstance(used, (float, int)):
            raise ValueError("Invalid quota")
        reset, duration = w.get("resetsAt"), w.get("windowDurationMins")
        if (not math.isfinite(used) or not 0 <= used <= 100 or
                isinstance(reset, bool) or not isinstance(reset, int) or reset <= 0 or
                isinstance(duration, bool) or not isinstance(duration, int) or duration <= 0):
            raise ValueError("Invalid quota window")
        result[key] = {"used_percent": used, "resets_at": reset, "window_minutes": duration}
    return result


def _codex_rpc(executable: Path, home: Path, timeout: float = 20) -> dict:
    """Short-lived stdio RPC; no prompts, model calls, or token handling."""
    import queue
    import subprocess
    import threading
    import time

    env = os.environ.copy()
    env["CODEX_HOME"] = str(Path(env.get("CODEX_HOME") or home / ".codex"))
    proc = subprocess.Popen(
        [str(executable), "app-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True, encoding="utf-8", env=env, cwd=str(home),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    messages = queue.Queue()
    def read_messages():
        try:
            for line in proc.stdout:
                try:
                    value = json.loads(line)
                    if isinstance(value, dict):
                        messages.put(value)
                except ValueError:
                    continue
        finally:
            messages.put(None)
    reader = threading.Thread(target=read_messages, daemon=True)
    reader.start()
    deadline = time.monotonic() + timeout
    def send(value):
        proc.stdin.write(json.dumps(value) + "\n")
        proc.stdin.flush()
    def receive(request_id):
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError()
            value = messages.get(timeout=remaining)
            if value is None:
                raise RuntimeError("Codex disconnected")
            if value.get("id") == request_id:
                if "error" in value or not isinstance(value.get("result"), dict):
                    raise RuntimeError("Codex request failed")
                return value["result"]
    try:
        send({"id": 1, "method": "initialize", "params": {
            "clientInfo": {"name": "usage_monitor", "version": __version__}}})
        receive(1)
        send({"method": "initialized"})
        send({"id": 2, "method": "account/rateLimits/read", "params": {}})
        return receive(2)
    finally:
        proc.kill()
        proc.wait(timeout=5)
        reader.join(timeout=1)
        for stream in (proc.stdin, proc.stdout):
            if stream:
                stream.close()


def fetch_codex_usage(home: Path) -> dict:
    executable = codex_executable(home)
    if not executable:
        return {"status": "missing_cli", "detail": "公式Codexをインストールしてログインしてください"}
    try:
        return {"status": "ok", "rate_limits": codex_rate_limits(_codex_rpc(executable, home))}
    except Exception:
        # Server errors may include private account details; never display them.
        return {"status": "error", "detail": "Codex使用量を取得できません。公式Codexのログイン状態と接続を確認してください"}


def scan_codex(home: Path) -> dict:
    base = (Path(os.environ.get("CODEX_HOME") or home / ".codex") if _same_home(home)
            else home / ".codex") / "sessions"
    files = sorted(base.rglob("*.jsonl")) if base.exists() else []
    total_in = total_out = total_cached = 0
    sessions_with_tokens = 0
    latest_rl = None
    latest_rl_epoch = None
    latest_rl_file = ""
    context: dict = {}
    latest_ctx_ts = ""
    for f in files:
        last_usage = None
        try:
            with open(f, encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    if "token_count" not in line and "rate_limits" not in line:
                        continue
                    try:
                        d = json.loads(line)
                    except (ValueError, TypeError):
                        continue
                    if not isinstance(d, dict):
                        continue
                    payload = d.get("payload") or {}
                    if not isinstance(payload, dict):
                        continue
                    info = payload.get("info") or {}
                    if not isinstance(info, dict):
                        info = {}
                    tu = info.get("total_token_usage") or payload.get("total_token_usage")
                    if isinstance(tu, dict) and "input_tokens" in tu:
                        last_usage = tu
                    rl = payload.get("rate_limits")
                    if isinstance(rl, dict) and isinstance(rl.get("primary"), dict):
                        ts = d.get("timestamp")
                        epoch = iso_to_epoch(str(ts)) if ts else None
                        if (not ts and latest_rl_epoch is None) or (epoch is not None and
                                (latest_rl_epoch is None or epoch >= latest_rl_epoch)):
                            latest_rl, latest_rl_file = rl, f.name
                            if epoch is not None:
                                latest_rl_epoch = epoch
                    if "token_count" in line:
                        ts = str(d.get("timestamp", ""))
                        if ts >= latest_ctx_ts:
                            last = info.get("last_token_usage") or {}
                            try:
                                ctx_in = int(last.get("input_tokens") or 0)
                                win = int(info.get("model_context_window") or 0)
                            except (TypeError, ValueError, AttributeError):
                                continue
                            if win > 0:
                                latest_ctx_ts = ts
                                context = {"input": ctx_in, "window": win,
                                           "pct": round(ctx_in / win * 100, 1)}
        except OSError:
            continue
        if last_usage:
            sessions_with_tokens += 1
            total_in += int(last_usage.get("input_tokens") or 0)
            total_out += int(last_usage.get("output_tokens") or 0)
            total_cached += int(last_usage.get("cached_input_tokens") or 0)
    usage_status, usage_detail = "local_history", ""
    if _same_home(home):
        live = fetch_codex_usage(home)
        usage_status, usage_detail = live["status"], live.get("detail", "")
        if usage_status == "ok":
            latest_rl = live["rate_limits"]
            latest_rl_file = "official_app_server"
    return {
        "usage_status": usage_status,
        "usage_detail": usage_detail,
        "rate_observed_at": latest_rl_epoch if usage_status == "local_history" else None,
        "files": len(files),
        "sessions_with_tokens": sessions_with_tokens,
        "input": total_in,
        "output": total_out,
        "cached": total_cached,
        "total": total_in + total_out,
        "rate_limits": latest_rl or {},
        "rate_source": latest_rl_file,
        "has_rate": latest_rl is not None and usage_status in ("ok", "local_history"),
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
    import claude_export
    oauth = claude_export.read(claude_export.path(None if _same_home(home) else home))
    return {
        "files": len(files),
        "messages": msgs,
        "input": inp,
        "output": out,
        "cache_creation": cache_c,
        "cache_read": cache_r,
        "total": inp + out,
        "oauth": oauth,
        "quota_source": "statusline",
        "quota_cached": oauth.get("status") == "ok",
        "observed_at": oauth.get("observed_at"),
    }


# Retired compatibility interfaces: never read subscription credentials or poll OAuth.
def claude_token(home: Path, *, isolated: bool = False) -> str:
    return ""


def claude_has_creds(home: Path, *, isolated: bool = False) -> bool:
    return False


def _resolve_oauth_access(oauth: dict) -> str:
    return ""


def _refresh_oauth(refresh: str) -> str:
    return ""


def _cli_refresh_creds(home: Path) -> bool:
    return False


def claude_token_from_os_store() -> str:
    return ""


def _read_credential_store(target: str) -> str:
    return ""


def fetch_claude_oauth(home: Path, *, isolated: bool = False) -> dict:
    return {"status": "unsupported", "detail": "Use documented Claude statusline numeric export"}


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
        print(json.dumps({"codex": codex, "claude": claude}, ensure_ascii=True, indent=2))
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
        print(f"  rate-limit: unavailable ({codex.get('usage_detail') or 'no history'})")
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
        print("  subscription usage: no observation. Configure numeric statusline export in the GUI settings and use official Claude Code.")
    elif oauth.get("status") == "expired":
        print("  subscription usage: token expired, auto-refresh failed.")
        print("  Use claude once (or wait); next refresh retries automatically.")
    else:
        print(f"  subscription usage: error ({oauth.get('detail', '?')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


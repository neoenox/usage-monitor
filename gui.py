#!/usr/bin/env python3
"""usage-monitor GUI (tkinter, stdlib only). CLIと同じ集計ロジックを再利用."""
from __future__ import annotations

import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk

import history as h
import monitor as m


STARTUP_LNK = "usage-monitor.lnk"


def startup_dir() -> Path:
    return Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def autostart_target() -> list[str]:
    import sys

    if getattr(sys, "frozen", False):
        return [sys.executable, "--tray"]
    return [sys.executable, str(Path(__file__).resolve()), "--tray"]


def autostart_enabled() -> bool:
    return (startup_dir() / STARTUP_LNK).exists()


def set_autostart(on: bool) -> bool:
    """スタートアップのショートカットを作成/削除。成功時True。"""
    import subprocess

    lnk = startup_dir() / STARTUP_LNK
    try:
        if on:
            tgt = autostart_target()
            target = str(tgt[0]).replace("'", "''")
            arguments = subprocess.list2cmdline(tgt[1:]).replace("'", "''")
            working_dir = (
                Path(tgt[1]).parent if len(tgt) > 2 else Path(tgt[0]).parent
            )
            working = str(working_dir).replace("'", "''")
            ps = (
                f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}');"
                f"$s.TargetPath='{target}';$s.Arguments='{arguments}';"
                f"$s.WorkingDirectory='{working}';$s.Save()"
            )
            subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True,
                           capture_output=True, timeout=30)
        else:
            lnk.unlink(missing_ok=True)
        return True
    except Exception:
        return False


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Usage Monitor - codex + claude")
        self.geometry("560x920")
        self._build()
        self._tick_job: str | None = None
        self.refresh()

    def _build(self) -> None:
        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)

        ttk.Label(root, text="Usage Monitor (snapshot)", font=("", 13, "bold")).pack(anchor="w")

        # Codex
        cx = ttk.LabelFrame(root, text="Codex", padding=10)
        cx.pack(fill="x", pady=8)
        self.cx_info = ttk.Label(cx, text="...")
        self.cx_info.pack(anchor="w")
        self.cx_tok = ttk.Label(cx, text="...", font=("", 10))
        self.cx_tok.pack(anchor="w")
        ttk.Label(cx, text="5h").pack(anchor="w")
        self.bar5 = ttk.Progressbar(cx, maximum=100, length=440)
        self.bar5.pack(fill="x")
        self.lbl5 = ttk.Label(cx, text="", wraplength=430, justify="left")
        self.lbl5.pack(anchor="w")
        ttk.Label(cx, text="weekly").pack(anchor="w")
        self.barW = ttk.Progressbar(cx, maximum=100, length=440)
        self.barW.pack(fill="x")
        self.lblW = ttk.Label(cx, text="", wraplength=430, justify="left")
        self.lblW.pack(anchor="w")
        ttk.Label(cx, text="context (現セッション)").pack(anchor="w")
        self.barCtx = ttk.Progressbar(cx, maximum=100, length=440)
        self.barCtx.pack(fill="x")
        self.lblCtx = ttk.Label(cx, text="")
        self.lblCtx.pack(anchor="w")

        # Claude
        cl = ttk.LabelFrame(root, text="Claude", padding=10)
        cl.pack(fill="x", pady=8)
        self.cl_info = ttk.Label(cl, text="...")
        self.cl_info.pack(anchor="w")
        self.cl_tok = ttk.Label(cl, text="...", font=("", 10))
        self.cl_tok.pack(anchor="w")
        ttk.Label(cl, text="サブスク 5h").pack(anchor="w")
        self.cl_bar5 = ttk.Progressbar(cl, maximum=100, length=440)
        self.cl_bar5.pack(fill="x")
        self.cl_lbl5 = ttk.Label(cl, text="", wraplength=430, justify="left")
        self.cl_lbl5.pack(anchor="w")
        ttk.Label(cl, text="サブスク weekly").pack(anchor="w")
        self.cl_barW = ttk.Progressbar(cl, maximum=100, length=440)
        self.cl_barW.pack(fill="x")
        self.cl_lblW = ttk.Label(cl, text="", wraplength=430, justify="left")
        self.cl_lblW.pack(anchor="w")
        self.cl_models = ttk.Label(cl, text="", font=("", 9))
        self.cl_models.pack(anchor="w")

        # 推移グラフ
        hist = ttk.LabelFrame(root, text="推移（5h使用%）", padding=10)
        hist.pack(fill="x", pady=8)
        self.chart = tk.Canvas(hist, width=440, height=230, bg="white", highlightthickness=1,
                               highlightbackground="#ccc")
        self.chart.pack()

        # controls
        row = ttk.Frame(root)
        row.pack(fill="x", pady=8)
        ttk.Button(row, text="更新", command=self.refresh).pack(side="left")
        self.btn_auto = ttk.Button(row, text="", command=self.toggle_autostart)
        self.btn_auto.pack(side="left", padx=6)
        self._sync_autostart_btn()
        self.status = ttk.Label(row, text="")
        self.status.pack(side="left", padx=6)

    def refresh(self) -> None:
        self.status.config(text="集計中...")
        th = threading.Thread(target=self._load, daemon=True)
        th.start()

    def _load(self) -> None:
        home = Path.home()
        codex = m.scan_codex(home)
        claude = m.scan_claude(home)
        self.after(0, lambda: self._render(codex, claude))

    def _render(self, codex: dict, claude: dict) -> None:
        self._last = (codex, claude)
        rl = codex.get("rate_limits", {}) or {}
        pri = rl.get("primary", {}) or {}
        sec = rl.get("secondary", {}) or {}
        plan = rl.get("plan_type", "-")
        p_used = float(pri.get("used_percent") or 0)
        s_used = float(sec.get("used_percent") or 0)

        self.cx_info.config(text=f"sessions {codex['files']} (tokenあり {codex['sessions_with_tokens']}) plan={plan}")
        self.cx_tok.config(
            text=f"in {m.fmt_num(codex['input'])} / out {m.fmt_num(codex['output'])} / total {m.fmt_num(codex['total'])}"
        )
        self.bar5["value"] = 100 - p_used
        self.lbl5.config(text=self._codex_label("5h", p_used, pri.get("resets_at"), m.fmt_ts,
                                                m.pace_label(p_used, 300, pri.get("resets_at"),
                                                             h.recent("codex_5h"))))
        self.barW["value"] = 100 - s_used
        self.lblW.config(text=self._codex_label("週", s_used, sec.get("resets_at"), m.fmt_ts,
                                                m.pace_label(s_used, 10080, sec.get("resets_at"),
                                                             h.recent("codex_wk"))
                                                + f" <{m.week_pace(s_used, 10080, sec.get('resets_at'))}>"))
        ctx = codex.get("context", {}) or {}
        if ctx:
            self.barCtx["value"] = ctx["pct"]
            self.lblCtx.config(text=f"{ctx['pct']}% ({m.fmt_num(ctx['input'])}/{m.fmt_num(ctx['window'])})")
        else:
            self.barCtx["value"] = 0
            self.lblCtx.config(text="-")

        self.cl_info.config(text=f"transcripts {claude['files']} messages {claude['messages']} (履歴は自動消去済)")
        self.cl_tok.config(
            text=f"in {m.fmt_num(claude['input'])} / out {m.fmt_num(claude['output'])} / total {m.fmt_num(claude['total'])}"
        )
        oauth = claude.get("oauth", {}) or {}
        cl5 = clw = None
        if oauth.get("status") == "ok":
            for bar, lbl, key, tag in ((self.cl_bar5, self.cl_lbl5, "five_hour", "5h"),
                                       (self.cl_barW, self.cl_lblW, "seven_day", "週")):
                w = oauth.get(key, {}) or {}
                try:
                    used = float(w.get("utilization"))
                except (TypeError, ValueError):
                    bar["value"] = 0
                    lbl.config(text="-")
                    continue
                bar["value"] = 100 - used
                win_min = 300 if key == "five_hour" else 10080
                hist_key = "claude_5h" if key == "five_hour" else "claude_wk"
                pace = m.pace_label(used, win_min, m.iso_to_epoch(w.get("resets_at")),
                                    h.recent(hist_key))
                extra = (f" <{m.week_pace(used, 10080, m.iso_to_epoch(w.get('resets_at')))}>"
                         if key == "seven_day" else "")
                lbl.config(text=f"{tag} 残り{100 - used:.0f}% (使用{used:.0f}%) "
                                f"reset={m.fmt_ts_iso(w.get('resets_at'))} ({m.fmt_countdown(w.get('resets_at'))}) [{pace}]{extra}")
                if key == "five_hour":
                    cl5 = used
                else:
                    clw = used
            self.cl_models.config(text=self._models_label(oauth))
        elif oauth.get("status") in ("missing_token", "expired"):
            self.cl_bar5["value"] = 0
            self.cl_barW["value"] = 0
            if oauth.get("status") == "expired":
                self.cl_lbl5.config(text="トークン期限切れ: claudeを一度使うと自動復旧します")
            else:
                self.cl_lbl5.config(text="未設定: claude auth login を実行してください")
            self.cl_lblW.config(text="")
            self.cl_models.config(text="")
        else:
            self.cl_bar5["value"] = 0
            self.cl_barW["value"] = 0
            self.cl_lbl5.config(text=f"取得エラー: {oauth.get('detail', '?')}")
            self.cl_lblW.config(text="")
            self.cl_models.config(text="")

        # 履歴記録＋グラフ
        try:
            metrics = {"codex_5h": p_used, "codex_wk": s_used}
            resets = {"codex_5h": pri.get("resets_at"), "codex_wk": sec.get("resets_at")}
            if cl5 is not None:
                metrics["claude_5h"] = cl5
            if clw is not None:
                metrics["claude_wk"] = clw
            h.record(metrics, resets)
        except Exception:
            pass
        self._draw_chart()

        from datetime import datetime

        self.status.config(text=f"更新: {datetime.now().strftime('%H:%M:%S')}")
        if getattr(self, "tray", None):
            self.tray.update_from(codex, claude)
        self._schedule_tick()

    @staticmethod
    def _codex_label(tag: str, used: float, resets_at, fmter, pace: str = "") -> str:
        base = (f"{tag} 残り{100 - used:.0f}% (使用{used:.0f}%) "
                f"reset={fmter(resets_at)} ({m.fmt_countdown(resets_at)})")
        return f"{base} [{pace}]" if pace else base

    @staticmethod
    def _models_label(oauth: dict) -> str:
        parts = []
        for tag, key in (("Opus週", "seven_day_opus"), ("Sonnet週", "seven_day_sonnet")):
            w = oauth.get(key, {}) or {}
            try:
                u = float(w.get("utilization"))
                parts.append(f"{tag}使用{u:.0f}%")
            except (TypeError, ValueError):
                continue
        return " / ".join(parts)

    def _schedule_tick(self) -> None:
        if self._tick_job is not None:
            try:
                self.after_cancel(self._tick_job)
            except tk.TclError:
                pass
        self._tick_job = self.after(60 * 1000, self._tick)

    def _tick(self) -> None:
        """1分毎にcountdown・ペース部分だけ更新。"""
        self._tick_job = None
        if not hasattr(self, "_last"):
            self._schedule_tick()
            return
        codex, claude = self._last
        rl = codex.get("rate_limits", {}) or {}
        pri = rl.get("primary", {}) or {}
        sec = rl.get("secondary", {}) or {}
        try:
            pu, su = float(pri.get("used_percent") or 0), float(sec.get("used_percent") or 0)
            self.lbl5.config(text=self._codex_label(
                "5h", pu, pri.get("resets_at"), m.fmt_ts,
                m.pace_label(pu, 300, pri.get("resets_at"), h.recent("codex_5h"))))
            self.lblW.config(text=self._codex_label(
                "週", su, sec.get("resets_at"), m.fmt_ts,
                m.pace_label(su, 10080, sec.get("resets_at"), h.recent("codex_wk"))
                + f" <{m.week_pace(su, 10080, sec.get('resets_at'))}>"))
        except (TypeError, ValueError):
            pass
        oauth = claude.get("oauth", {}) or {}
        if oauth.get("status") == "ok":
            for lbl, key, tag, win_min, hist_key in (
                    (self.cl_lbl5, "five_hour", "5h", 300, "claude_5h"),
                    (self.cl_lblW, "seven_day", "週", 10080, "claude_wk")):
                w = oauth.get(key, {}) or {}
                try:
                    used = float(w.get("utilization"))
                    pace = m.pace_label(used, win_min, m.iso_to_epoch(w.get("resets_at")),
                                        h.recent(hist_key))
                    extra = (f" <{m.week_pace(used, 10080, m.iso_to_epoch(w.get('resets_at')))}>"
                             if key == "seven_day" else "")
                    lbl.config(text=f"{tag} 残り{100 - used:.0f}% (使用{used:.0f}%) "
                                    f"reset={m.fmt_ts_iso(w.get('resets_at'))} ({m.fmt_countdown(w.get('resets_at'))}) [{pace}]{extra}")
                except (TypeError, ValueError):
                    pass
        self._schedule_tick()

    def _draw_chart(self) -> None:
        from datetime import datetime

        c = self.chart
        c.delete("all")
        W, H, pad_l, pad_b, panels = 440, 230, 34, 16, [("Codex", "codex_5h", "#22c55e"),
                                                        ("Claude", "claude_5h", "#3b82f6")]
        ph = (H - pad_b) // 2
        for idx, (name, metric, color) in enumerate(panels):
            y0 = idx * ph
            pts = h.recent(metric, hours=72)[-48:]
            # 枠・グリッド・Y目盛
            c.create_rectangle(pad_l, y0 + 4, W - 4, y0 + ph - pad_b // 2, outline="#ccc")
            for gv, gl in ((0, "0"), (50, "50"), (100, "100")):
                gy = y0 + 4 + (ph - pad_b // 2 - 4) * (1 - gv / 100)
                c.create_line(pad_l, gy, W - 4, gy, fill="#eee")
                c.create_text(pad_l - 3, gy, anchor="e", text=gl, fill="#888", font=("", 8))
            c.create_text(pad_l + 2, y0 + 12, anchor="w", text=name, fill="#555",
                          font=("", 9, "bold"))
            if not pts:
                c.create_text(W // 2, y0 + ph // 2, text="履歴なし（更新を重ねると表示）", fill="#888")
                continue
            n = len(pts)
            bw = (W - 4 - pad_l) / 48
            off = 48 - n
            for i, (_, used) in enumerate(pts):
                x0 = pad_l + (off + i) * bw
                hh = min(100.0, max(0.0, used)) / 100 * (ph - pad_b // 2 - 4)
                c.create_rectangle(x0, y0 + ph - pad_b // 2 - hh, x0 + max(bw - 1, 1),
                                   y0 + ph - pad_b // 2, fill=color, outline="")
            t0 = datetime.fromtimestamp(pts[0][0]).strftime("%H:%M")
            t1 = datetime.fromtimestamp(pts[-1][0]).strftime("%H:%M")
            c.create_text(pad_l, y0 + ph - 2, anchor="w", text=t0, fill="#888", font=("", 8))
            c.create_text(W - 6, y0 + ph - 2, anchor="e", text=t1, fill="#888", font=("", 8))
            c.create_text(W - 6, y0 + 12, anchor="e", text=f"最新{pts[-1][1]:.0f}%",
                          fill=color, font=("", 9, "bold"))

    def toggle_autostart(self) -> None:
        ok = set_autostart(not autostart_enabled())
        if ok:
            self._sync_autostart_btn()

    def _sync_autostart_btn(self) -> None:
        self.btn_auto.config(text=f"自動起動:{'ON' if autostart_enabled() else 'OFF'}")


def tray_icon_image(pct_left: float):
    """残量%に応じた色丸アイコン (緑/黄/赤)。"""
    from PIL import Image, ImageDraw

    v = max(0.0, min(100.0, float(pct_left)))
    color = "#22c55e" if v >= 50 else ("#f59e0b" if v >= 20 else "#ef4444")
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([6, 6, 58, 58], fill=color)
    return img


def tray_tooltip(codex: dict, claude: dict) -> str:
    rl = codex.get("rate_limits", {}) or {}
    pri = rl.get("primary", {}) or {}
    sec = rl.get("secondary", {}) or {}
    try:
        cx5 = 100 - float(pri.get("used_percent") or 0)
    except (TypeError, ValueError):
        cx5 = -1
    try:
        cxw = 100 - float(sec.get("used_percent") or 0)
    except (TypeError, ValueError):
        cxw = -1
    oauth = claude.get("oauth", {}) or {}
    if oauth.get("status") == "ok":
        def left(key: str) -> str:
            try:
                return f"{100 - float((oauth.get(key) or {}).get('utilization')):.0f}%"
            except (TypeError, ValueError):
                return "-"

        cl = f"Claude 5h残り{left('five_hour')} / 週残り{left('seven_day')}"
    else:
        cl = "Claude サブスク未取得"
    return (
        f"Codex 5h残り{cx5:.0f}% / 週残り{cxw:.0f}%\n{cl}"
        if cx5 >= 0
        else cl
    )


class TrayController:
    """タスクトレイ常駐: ホバー表示・5分毎更新・左クリックで開く・制限接近アラート。"""

    WARN_AT = 20.0
    CRIT_AT = 10.0
    REARM_ABOVE = 25.0

    def __init__(self, app: "App") -> None:
        import tray_win32

        self.app = app
        self.notified: dict[str, str] = {}
        self.tray = tray_win32.Win32Tray(
            "Usage Monitor 起動中...",
            on_open=lambda: app.after(0, self._show),
            on_refresh=lambda: app.after(0, app.refresh),
            on_quit=lambda: app.after(0, self._quit),
        )

    @staticmethod
    def _ico_path() -> str:
        d = h.db_path().parent
        return str(d / "tray.ico")

    def start(self) -> None:
        import tray_win32

        tray_win32.run_threaded(self.tray)
        self._schedule()

    def _schedule(self) -> None:
        self.app.after(5 * 60 * 1000, self._auto)

    def _auto(self) -> None:
        self.app.refresh()
        self._schedule()

    def update_from(self, codex: dict, claude: dict) -> None:
        self.tray.set_tooltip(tray_tooltip(codex, claude))
        rl = codex.get("rate_limits", {}) or {}
        try:
            left = 100 - float((rl.get("primary", {}) or {}).get("used_percent") or 0)
        except (TypeError, ValueError):
            left = 100
        tray_icon_image(left).save(self._ico_path(), format="ICO", sizes=[(64, 64)])
        self.tray.set_icon(self._ico_path())
        self._check_alerts(codex, claude)

    @staticmethod
    def alert_for(left: float, prev: str | None) -> str | None:
        """純粋関数: 残量と前回通知状態から今回の通知レベル。テスト容易化のため分離。"""
        if left <= TrayController.CRIT_AT:
            return None if prev == "crit" else "crit"
        if left <= TrayController.WARN_AT:
            return None if prev in ("warn", "crit") else "warn"
        return None

    def _check_alerts(self, codex: dict, claude: dict) -> None:
        from datetime import datetime

        metrics: list[tuple[str, float, str]] = []
        rl = codex.get("rate_limits", {}) or {}
        for name, key, fmter in (
            ("Codex 5h", "primary", m.fmt_ts),
            ("Codex 週", "secondary", m.fmt_ts),
        ):
            w = rl.get(key, {}) or {}
            try:
                left = 100 - float(w.get("used_percent") or 0)
            except (TypeError, ValueError):
                continue
            metrics.append((name, left, f"リセット{fmter(w.get('resets_at'))}"))
        oauth = claude.get("oauth", {}) or {}
        if oauth.get("status") == "ok":
            for name, key in (("Claude 5h", "five_hour"), ("Claude 週", "seven_day")):
                w = oauth.get(key, {}) or {}
                try:
                    left = 100 - float(w.get("utilization"))
                except (TypeError, ValueError):
                    continue
                metrics.append((name, left, f"リセット{m.fmt_ts_iso(w.get('resets_at'))}"))
        for name, left, extra in metrics:
            if left > self.REARM_ABOVE:
                self.notified.pop(name, None)
                continue
            level = self.alert_for(left, self.notified.get(name))
            if level is None:
                continue
            self.notified[name] = level
            mark = "【要節約】" if level == "crit" else "【注意】"
            try:
                self.tray.balloon(f"{mark}使用量アラート",
                                  f"{name} 残り{left:.0f}% ({extra})",
                                  warn=(level == "crit"))
            except Exception:
                pass

    def _show(self) -> None:
        self.app.deiconify()
        try:
            self.app.lift()
            self.app.focus_force()
        except Exception:
            pass

    def _quit(self) -> None:
        try:
            self.tray.stop()
        except Exception:
            pass
        self.app.destroy()


if __name__ == "__main__":
    import sys

    app = App()
    if "--tray" in sys.argv:
        app.tray = TrayController(app)
        app.tray.start()
        app.withdraw()
        app.protocol("WM_DELETE_WINDOW", app.withdraw)
    app.mainloop()

#!/usr/bin/env python3
"""usage-monitor GUI (tkinter, stdlib only). CLIと同じ集計ロジックを再利用."""
from __future__ import annotations

import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk

import history as h
import monitor as m
import settings


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


def remaining_text(text: str) -> tuple[str, str]:
    """Split quota summaries into a prominent remaining value and readable details."""
    import re

    match = re.search(r"残り(-?[\d.]+)% \(使用[\d.]+%\)", text)
    if not match:
        return "", text
    headline = f"残り {match.group(1)}%"
    detail = text[match.end():].strip().replace("reset=", "リセット：")
    detail = detail.replace(" [", "\n予測：").replace("]", "")
    return headline, detail


def quota_forecast(used, window_min, reset_epoch, hist=(), show_date=True) -> str:
    """Explain a forecast only when comparable samples establish a recent rate."""
    import math
    import time

    now = time.time()
    try:
        used, reset_epoch = float(used), float(reset_epoch)
        if not math.isfinite(used) or not math.isfinite(reset_epoch) or window_min <= 0:
            return "データ不足で予測できません"
    except (TypeError, ValueError):
        return "データ不足で予測できません"
    if reset_epoch <= now:
        return "リセット後のデータを待っています"
    if used >= 100:
        return "利用上限に達しています"
    start = reset_epoch - window_min * 60
    points = sorted((t, u) for t, u in hist if start <= t <= now)
    if len(points) < 2 or points[-1][0] - points[0][0] < 600:
        return "履歴不足で予測できません"
    delta = points[-1][1] - points[0][1]
    if any(b[1] < a[1] for a, b in zip(points, points[1:])) or used < points[-1][1]:
        return "履歴不足で予測できません"
    if delta == 0:
        return "リセットまで持つ見込み"
    # Treat the current snapshot as the newest observation when usage advanced.
    # This avoids letting stale/invalid historical 0% samples dominate the slope.
    if now > points[-1][0] and used > points[-1][1]:
        points.append((now, used))
        delta = points[-1][1] - points[0][1]
    rate = delta / (points[-1][0] - points[0][0])
    # The remaining quota belongs to the current snapshot, so forecast from now.
    hit = now + (100 - used) / rate
    if hit >= reset_epoch:
        return "リセットまで持つ見込み"
    if hit <= now:
        return "上限に達する見込み（予測時刻を経過）"
    minutes = max(1, math.ceil((hit - now) / 60))
    days, rest = divmod(minutes, 1440)
    hours, minutes = divmod(rest, 60)
    duration = (f"{days}日" if days else "") + (f"{hours}時間" if hours else "") + (f"{minutes}分" if minutes else "")
    return f"約{duration}後に上限へ達する見込み"



def history_snapshot(codex: dict, p_used: float, s_used: float,
                     cl5: float | None = None, clw: float | None = None,
                     pri: dict | None = None, sec: dict | None = None
                     ) -> tuple[dict[str, float], dict[str, int | None]]:
    """Build only history samples that were actually observed."""
    metrics: dict[str, float] = {}
    resets: dict[str, int | None] = {}
    if codex.get("has_rate"):
        metrics.update({"codex_5h": p_used, "codex_wk": s_used})
        pri, sec = pri or {}, sec or {}
        resets.update({
            "codex_5h": pri.get("resets_at"),
            "codex_wk": sec.get("resets_at"),
        })
    if cl5 is not None:
        metrics["claude_5h"] = cl5
    if clw is not None:
        metrics["claude_wk"] = clw
    return metrics, resets

def quota_state(left: float, cfg: dict) -> tuple[str, str]:
    if left <= cfg["crit_at"]:
        return "残量わずか", "#b91c1c"
    if left <= cfg["warn_at"]:
        return "注意", "#92400e"
    return "余裕あり", "#166534"


def freshness_text(elapsed: float) -> str:
    minutes = max(0, int(elapsed // 60))
    return "最終更新：たった今" if minutes == 0 else f"最終更新：{minutes}分前"


class RemainingLabel(ttk.Frame):
    """Quota label compatible with the existing render and countdown updates."""

    def __init__(self, parent):
        super().__init__(parent)
        self.heading = ttk.Frame(self)
        self.heading.pack(fill="x")
        self.value = ttk.Label(self.heading, style="Remaining.TLabel")
        self.value.pack(side="left")
        self.badge = ttk.Label(self.heading)
        self.badge.pack(side="left", padx=12)
        self.detail = ttk.Label(self, justify="left", style="Hint.TLabel")
        self.detail.pack(fill="x")
        self.bind("<Configure>", lambda event: self.detail.configure(wraplength=max(100, event.width)))

    def cget(self, key):
        if key == "text":
            return getattr(self, "_text", "")
        return super().cget(key)

    def config(self, *, text):
        self._text = text
        headline, detail = remaining_text(text)
        self.value.configure(text=headline)
        if headline:
            self.heading.pack(fill="x", before=self.detail)
            state, color = quota_state(float(headline.split()[1][:-1]), settings.load())
            self.badge.configure(text=state, foreground=color)
            if hasattr(self, "bar"):
                self.bar.configure(style=f"{state}.Horizontal.TProgressbar")
        else:
            self.heading.pack_forget()
            if hasattr(self, "bar"):
                self.bar.configure(style="Unavailable.Horizontal.TProgressbar")
        self.detail.configure(text=detail)


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"Usage Monitor v{m.__version__} - codex + claude")
        self.geometry("600x740")
        self._tick_job: str | None = None
        self._set_window_icon()
        self._build()
        self._fit_overview()
        self.refresh()

    def _fit_overview(self) -> None:
        """Size the initial window for all quota rows, including wrapped details."""
        self.update_idletasks()
        # Rendered quota details use two lines; reserve these before data arrives.
        labels = (self.lbl5, self.lblW, self.cl_lbl5, self.cl_lblW)
        for label in labels:
            label.config(text="5h 残り100% (使用0%) reset=00:00 (残り時間) [利用ペース]")
        self.cl_models.configure(text="Opus週使用0% / Sonnet週使用0%")
        self.update_idletasks()
        canvas = self.overview_canvas
        content_height = canvas.bbox("all")[3]
        chrome_height = self.winfo_height() - canvas.winfo_height()
        height = min(content_height + chrome_height + 24, self.winfo_screenheight() - 80)
        self.geometry(f"{self.overview_width}x{height}")
        self.update_idletasks()
        content_height = canvas.bbox("all")[3]
        chrome_height = self.winfo_height() - canvas.winfo_height()
        height = min(content_height + chrome_height + 24, self.winfo_screenheight() - 80)
        self.geometry(f"{self.overview_width}x{height}+40+40")
        for label in labels:
            label.config(text="読み込み中…")
        self.cl_models.configure(text="")
        self.update_idletasks()
        canvas.yview_moveto(0)

    def _set_window_icon(self) -> None:
        """タイトルバー左上のアイコン (exe埋め込みとは別に必要)。"""
        try:
            from PIL import Image, ImageDraw

            S = 64
            img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            d.rounded_rectangle([2, 2, S - 2, S - 2], radius=13, fill=(17, 24, 39, 255))
            d.arc([11, 11, S - 11, S - 11], start=-90, end=180, fill=(34, 197, 94, 255), width=7)
            d.arc([11, 11, S - 11, S - 11], start=180, end=270, fill=(55, 65, 81, 255), width=7)
            d.ellipse([S // 2 - 6, S // 2 - 6, S // 2 + 6, S // 2 + 6], fill=(59, 130, 246, 255))
            p = h.db_path().parent / "window.ico"
            img.save(str(p), format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
            self.iconbitmap(str(p))
        except Exception:
            pass

    def _build(self) -> None:
        self.minsize(520, 640)
        style = ttk.Style(self)
        style.theme_use("clam")
        for name, color in (("余裕あり", "#166534"), ("注意", "#b45309"), ("残量わずか", "#b91c1c"), ("Unavailable", "#6b7280")):
            style.configure(f"{name}.Horizontal.TProgressbar", background=color)
        style.configure("Remaining.TLabel", font=("Yu Gothic UI", 20, "bold"))
        style.configure("Title.TLabel", font=("Yu Gothic UI", 16, "bold"))
        style.configure("Hint.TLabel", foreground="#555555")
        root = ttk.Frame(self, padding=16)
        root.pack(fill="both", expand=True)
        header = ttk.Frame(root)
        header.pack(fill="x", pady=(0, 12))
        ttk.Label(header, text="Usage Monitor", style="Title.TLabel").pack(side="left")
        self.btn_refresh = ttk.Button(header, text="最新情報に更新", command=self.refresh)
        self.btn_refresh.pack(side="right")
        self.status = ttk.Label(root, text="", style="Hint.TLabel", wraplength=480)
        self.status.pack(anchor="w", pady=(0, 4))
        self.freshness = ttk.Label(root, text="最終更新：未取得", style="Hint.TLabel")
        self.freshness.pack(anchor="w", pady=(0, 8))
        tabs = ttk.Notebook(root)
        tabs.pack(fill="both", expand=True)
        overview_page = ttk.Frame(tabs)
        overview_canvas = tk.Canvas(overview_page, highlightthickness=0)
        scroll = ttk.Scrollbar(overview_page, orient="vertical", command=overview_canvas.yview)
        overview_canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        overview_canvas.pack(side="left", fill="both", expand=True)
        overview = ttk.Frame(overview_canvas, padding=12)
        content = overview_canvas.create_window((0, 0), window=overview, anchor="nw")
        overview.bind("<Configure>", lambda event: overview_canvas.configure(scrollregion=overview_canvas.bbox("all")))
        overview_canvas.bind("<Configure>", lambda event: overview_canvas.itemconfigure(content, width=event.width))
        self.overview_canvas = overview_canvas
        self.bind("<MouseWheel>", lambda event: overview_canvas.yview_scroll(-int(event.delta / 120), "units")
                  if tabs.index(tabs.select()) == 0 else None)
        trend = ttk.Frame(tabs, padding=12)
        config = ttk.Frame(tabs, padding=12)
        for frame, title in ((overview_page, "概要"), (trend, "推移"), (config, "設定")):
            tabs.add(frame, text=title)
        ttk.Label(overview, text="バーは利用枠の残量を表します", style="Hint.TLabel").pack(anchor="w")

        def window(parent, title):
            row = ttk.Frame(parent)
            row.pack(fill="x", pady=(8, 0))
            ttk.Label(row, text=title, font=("Yu Gothic UI", 10, "bold")).pack(anchor="w")
            label = RemainingLabel(row)
            label.pack(fill="x")
            bar = ttk.Progressbar(row, maximum=100)
            bar.pack(fill="x", pady=(4, 0))
            label.bar = bar
            return bar, label

        providers = ttk.Frame(overview)
        providers.pack(fill="x")
        compact = self.winfo_screenheight() < 900
        self.overview_width = min(1000, self.winfo_screenwidth() - 80) if compact else 600
        cx = ttk.LabelFrame(providers, text="Codex", padding=10)
        if compact:
            providers.columnconfigure((0, 1), weight=1, uniform="provider")
            cx.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=8)
        else:
            cx.pack(fill="x", pady=(8, 4))
        self.bar5, self.lbl5 = window(cx, "5時間の利用枠")
        self.barW, self.lblW = window(cx, "週間の利用枠")
        cl = ttk.LabelFrame(providers, text="Claude", padding=10)
        if compact:
            cl.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=8)
        else:
            cl.pack(fill="x", pady=4)
        self.cl_bar5, self.cl_lbl5 = window(cl, "5時間の利用枠")
        self.cl_barW, self.cl_lblW = window(cl, "週間の利用枠")
        self.cl_models = ttk.Label(cl, text="", style="Hint.TLabel")
        self.cl_models.pack(anchor="w", pady=(4, 0))

        ttk.Label(trend, text="5時間枠の使用率の推移（%）", font=("Yu Gothic UI", 12, "bold")).pack(anchor="w")
        ttk.Label(trend, text="直近72時間から最大48件を表示", style="Hint.TLabel").pack(anchor="w", pady=(4, 12))
        self.chart = tk.Canvas(trend, width=440, height=230, bg="white", highlightthickness=1,
                               highlightbackground="#cccccc")
        self.chart.pack(fill="x")
        self.chart.bind("<Configure>", lambda event: self._draw_chart())
        details = ttk.LabelFrame(trend, text="ローカル履歴の集計（参考値）", padding=10)
        details.pack(fill="x", pady=12)
        self.cx_info = ttk.Label(details, text="…", wraplength=440)
        self.cx_info.pack(anchor="w")
        self.cx_tok = ttk.Label(details, text="…")
        self.cx_tok.pack(anchor="w", pady=(0, 8))
        self.cl_info = ttk.Label(details, text="…", wraplength=440)
        self.cl_info.pack(anchor="w")
        self.cl_tok = ttk.Label(details, text="…")
        self.cl_tok.pack(anchor="w")
        ttk.Label(details, text="Codex：現在のセッションのコンテキスト使用率").pack(anchor="w", pady=(12, 4))
        self.barCtx = ttk.Progressbar(details, maximum=100)
        self.barCtx.pack(fill="x")
        self.lblCtx = ttk.Label(details, text="")
        self.lblCtx.pack(anchor="w")

        ttk.Label(config, text="通知", font=("Yu Gothic UI", 12, "bold")).pack(anchor="w")
        ttk.Label(config, text="トレイ常駐中、残量が指定値以下になると通知します。\n緊急は警告より小さい値に設定してください。",
                  style="Hint.TLabel", justify="left").pack(anchor="w", pady=8)
        fields = ttk.Frame(config)
        fields.pack(anchor="w")
        for index, (text, attr) in enumerate((("警告する残量", "ent_warn"), ("緊急通知する残量", "ent_crit"))):
            ttk.Label(fields, text=text).grid(row=index, column=0, sticky="w", pady=6)
            entry = ttk.Entry(fields, width=6)
            entry.grid(row=index, column=1, padx=12)
            ttk.Label(fields, text="%").grid(row=index, column=2)
            setattr(self, attr, entry)
        ttk.Button(config, text="通知設定を保存", command=self.save_thresholds).pack(anchor="w", pady=12)
        self._sync_threshold_entries()
        ttk.Separator(config).pack(fill="x", pady=12)
        ttk.Label(config, text="Windows起動時の動作", font=("Yu Gothic UI", 12, "bold")).pack(anchor="w")
        ttk.Label(config, text="有効にするとトレイに常駐します。", style="Hint.TLabel").pack(anchor="w", pady=8)
        self.btn_auto = ttk.Button(config, text="", command=self.toggle_autostart)
        self.btn_auto.pack(anchor="w")
        self._sync_autostart_btn()

    def save_thresholds(self) -> None:
        err = settings.save(self.ent_warn.get(), self.ent_crit.get())
        if err:
            self.status.config(text=err)
        else:
            self.status.config(text="閾値を保存しました")
            self._sync_threshold_entries()
            for label in (self.lbl5, self.lblW, self.cl_lbl5, self.cl_lblW):
                label.config(text=label.cget("text"))

    def _sync_threshold_entries(self) -> None:
        cfg = settings.load()
        for ent, key in ((self.ent_warn, "warn_at"), (self.ent_crit, "crit_at")):
            ent.delete(0, tk.END)
            ent.insert(0, str(cfg[key]))

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
        codex, claude = m.normalize_snapshot(codex, claude)
        self._last = (codex, claude)
        rl = codex.get("rate_limits", {}) or {}
        pri = rl.get("primary", {}) or {}
        sec = rl.get("secondary", {}) or {}
        plan = rl.get("plan_type", "-")
        p_used = float(pri.get("used_percent") or 0)
        s_used = float(sec.get("used_percent") or 0)

        self.cx_info.config(text=f"Codex：履歴 {codex['files']}件 / トークン記録 {codex['sessions_with_tokens']}件 / プラン {plan}")
        self.cx_tok.config(
            text=f"入力 {m.fmt_num(codex['input'])} / 出力 {m.fmt_num(codex['output'])} / 合計 {m.fmt_num(codex['total'])}"
        )
        if codex.get("has_rate"):
            self.bar5["value"] = 100 - p_used
            self.lbl5.config(text=self._codex_label(
                "5h", p_used, pri.get("resets_at"), m.fmt_ts,
                quota_forecast(p_used, 300, pri.get("resets_at"), h.recent("codex_5h"), False),
                codex.get("new_window_5h", False)))
            self.barW["value"] = 100 - s_used
            self.lblW.config(text=self._codex_label(
                "週", s_used, sec.get("resets_at"), m.fmt_ts,
                quota_forecast(s_used, 10080, sec.get("resets_at"), h.recent("codex_wk")),
                codex.get("new_window_wk", False)))
        else:
            self.bar5["value"] = 0
            self.barW["value"] = 0
            self.lbl5.config(text="未連携: codex login 後に「更新」")
            self.lblW.config(text="")
        ctx = codex.get("context", {}) or {}
        if ctx:
            self.barCtx["value"] = ctx["pct"]
            self.lblCtx.config(text=f"{ctx['pct']}% ({m.fmt_num(ctx['input'])}/{m.fmt_num(ctx['window'])})")
        else:
            self.barCtx["value"] = 0
            self.lblCtx.config(text="-")

        self.cl_info.config(text=f"Claude：履歴 {claude['files']}件 / メッセージ {claude['messages']}件（履歴の自動削除により参考値）")
        self.cl_tok.config(
            text=f"入力 {m.fmt_num(claude['input'])} / 出力 {m.fmt_num(claude['output'])} / 合計 {m.fmt_num(claude['total'])}"
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
                flag = "new_window_5h" if key == "five_hour" else "new_window_wk"
                pace = quota_forecast(used, win_min, m.iso_to_epoch(w.get("resets_at")),
                                    h.recent(hist_key), show_date=(key != "five_hour"))
                extra = ""
                if claude.get(flag):
                    extra += "（新窓）"
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
            metrics, resets = history_snapshot(codex, p_used, s_used, cl5, clw, pri, sec)
            if metrics:
                h.record(metrics, resets)
        except Exception:
            pass
        self._draw_chart()

        import time

        self._updated_at = time.monotonic()
        self.freshness.config(text=freshness_text(0))
        self.status.config(text="更新しました")
        if getattr(self, "tray", None):
            self.tray.update_from(codex, claude)
        self._schedule_tick()

    @staticmethod
    def _codex_label(tag: str, used: float, resets_at, fmter, pace: str = "", new_window: bool = False) -> str:
        base = (f"{tag} 残り{100 - used:.0f}% (使用{used:.0f}%) "
                f"reset={fmter(resets_at)} ({m.fmt_countdown(resets_at)})")
        if pace:
            base += f" [{pace}]"
        if new_window:
            base += "（新窓）"
        elif m.is_stale(resets_at):
            base += "（窓終了・新データ待ち）"
        return base

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
        if hasattr(self, "_updated_at"):
            import time
            self.freshness.config(text=freshness_text(time.monotonic() - self._updated_at))
        if not hasattr(self, "_last"):
            self._schedule_tick()
            return
        codex, claude = self._last
        if not codex.get("has_rate"):
            self._schedule_tick()
            return
        rl = codex.get("rate_limits", {}) or {}
        pri = rl.get("primary", {}) or {}
        sec = rl.get("secondary", {}) or {}
        try:
            pu, su = float(pri.get("used_percent") or 0), float(sec.get("used_percent") or 0)
            self.lbl5.config(text=self._codex_label(
                "5h", pu, pri.get("resets_at"), m.fmt_ts,
                quota_forecast(pu, 300, pri.get("resets_at"), h.recent("codex_5h"), False),
                codex.get("new_window_5h", False)))
            self.lblW.config(text=self._codex_label(
                "週", su, sec.get("resets_at"), m.fmt_ts,
                quota_forecast(su, 10080, sec.get("resets_at"), h.recent("codex_wk")),
                codex.get("new_window_wk", False)))
        except (TypeError, ValueError):
            pass
        oauth = claude.get("oauth", {}) or {}
        if oauth.get("status") == "ok":
            for lbl, key, tag, win_min, hist_key, flag in (
                    (self.cl_lbl5, "five_hour", "5h", 300, "claude_5h", "new_window_5h"),
                    (self.cl_lblW, "seven_day", "週", 10080, "claude_wk", "new_window_wk")):
                w = oauth.get(key, {}) or {}
                try:
                    used = float(w.get("utilization"))
                    pace = quota_forecast(used, win_min, m.iso_to_epoch(w.get("resets_at")),
                                        h.recent(hist_key), show_date=(key != "five_hour"))
                    extra = ""
                    if claude.get(flag):
                        extra += "（新窓）"
                    lbl.config(text=f"{tag} 残り{100 - used:.0f}% (使用{used:.0f}%) "
                                    f"reset={m.fmt_ts_iso(w.get('resets_at'))} ({m.fmt_countdown(w.get('resets_at'))}) [{pace}]{extra}")
                except (TypeError, ValueError):
                    pass
        self._schedule_tick()

    def _draw_chart(self) -> None:
        from datetime import datetime

        c = self.chart
        c.delete("all")
        W, H, pad_l, pad_b, panels = max(440, c.winfo_width()), 230, 34, 16, [("Codex", "codex_5h", "#22c55e"),
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


def _ring_color(left: float | None) -> str:
    if left is None:
        return "#9ca3af"
    v = max(0.0, min(100.0, left))
    return "#22c55e" if v >= 50 else ("#f59e0b" if v >= 20 else "#ef4444")


def _nearest_left(windows: list[tuple[float | None, int | None]]) -> float | None:
    """リセット最短の窓の残量%を返す。候補がなければNone (グレー表示)。"""
    dated = sorted((r, left) for left, r in windows if r and left is not None)
    if dated:
        return dated[0][1]
    valid = [left for left, _ in windows if left is not None]
    return valid[0] if valid else None


def tray_icon_image(codex: dict, claude: dict | None = None):
    """二重円: 外=Codex・内=Claude。各々リセット最短の窓の残量を弧で表示。"""
    from PIL import Image, ImageDraw

    if isinstance(codex, (int, float)):  # 旧呼出互換 (単一%→外円のみ)
        codex = {"rate_limits": {"primary": {"used_percent": 100 - float(codex)}}}
        claude = None
    rl = codex.get("rate_limits", {}) or {}
    cx_windows = []
    for key in ("primary", "secondary"):
        w = rl.get(key, {}) or {}
        try:
            left = 100 - float(w.get("used_percent"))
        except (TypeError, ValueError):
            left = None
        cx_windows.append((left, w.get("resets_at")))
    cx_left = _nearest_left(cx_windows) if codex.get("has_rate", True) else None

    cl_left = None
    oauth = (claude or {}).get("oauth", {}) or {}
    if oauth.get("status") == "ok":
        cl_windows = []
        for key in ("five_hour", "seven_day"):
            w = oauth.get(key, {}) or {}
            try:
                left = 100 - float(w.get("utilization"))
            except (TypeError, ValueError):
                left = None
            cl_windows.append((left, m.iso_to_epoch(w.get("resets_at"))))
        cl_left = _nearest_left(cl_windows)

    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for bbox, width, left in (([4, 4, 60, 60], 7, cx_left),
                              ([17, 17, 47, 47], 7, cl_left)):
        d.arc(bbox, 0, 360, fill="#374151", width=width)
        if left is not None:
            sweep = max(0.0, min(100.0, left)) / 100 * 360
            if sweep > 0:
                d.arc(bbox, -90, -90 + sweep, fill=_ring_color(left), width=width)
    return img


def tray_tooltip(codex: dict, claude: dict) -> str:
    if codex.get("has_rate"):
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
        cx = (f"Codex 5h残り{cx5:.0f}% / 週残り{cxw:.0f}%"
              if cx5 >= 0 else "Codex 未連携")
    else:
        cx = "Codex 未連携"
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
    return f"{cx}\n{cl}"


class TrayController:
    """タスクトレイ常駐: ホバー表示・5分毎更新・左クリックで開く・制限接近アラート。"""

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
        tray_icon_image(codex, claude).save(self._ico_path(), format="ICO", sizes=[(64, 64)])
        self.tray.set_icon(self._ico_path())
        self._check_alerts(codex, claude)
        self._maybe_daily_report(codex, claude)

    def _maybe_daily_report(self, codex: dict, claude: dict) -> None:
        """その日最初の更新時に前日のサマリーを1発通知。履歴がなければ出さない。"""
        import datetime
        import os as _os
        from pathlib import Path as _P

        import history as _h

        today = datetime.date.today().isoformat()
        mark = _P(_os.environ.get("LOCALAPPDATA", str(_P.home()))) / "usage-monitor" / ".daily_report"
        try:
            if mark.exists() and mark.read_text(encoding="utf-8").strip() == today:
                return
        except Exception:
            pass
        start, end = m.day_bounds(1)
        yesterday = {}
        for metric in ("codex_5h", "codex_wk", "claude_5h", "claude_wk"):
            try:
                yesterday[metric] = m.daily_max_used(_h.recent(metric, hours=72), start, end)
            except Exception:
                yesterday[metric] = None
        if all(v is None for v in yesterday.values()):
            return
        verdicts = {}
        sec = (codex.get("rate_limits", {}) or {}).get("secondary", {}) or {}
        try:
            verdicts["codex_wk"] = m.week_pace(float(sec.get("used_percent")), 10080,
                                               sec.get("resets_at"))
        except (TypeError, ValueError):
            pass
        oauth = claude.get("oauth", {}) or {}
        if oauth.get("status") == "ok":
            w = oauth.get("seven_day", {}) or {}
            try:
                verdicts["claude_wk"] = m.week_pace(
                    float(w.get("utilization")), 10080, m.iso_to_epoch(w.get("resets_at")))
            except (TypeError, ValueError):
                pass
        try:
            self.tray.balloon("朝の使用量レポート",
                              "\n".join(m.daily_report_lines(yesterday, verdicts)))
            mark.parent.mkdir(parents=True, exist_ok=True)
            mark.write_text(today, encoding="utf-8")
        except Exception:
            pass

    @staticmethod
    def alert_for(left: float, prev: str | None,
                  warn_at: float = 20.0, crit_at: float = 10.0) -> str | None:
        """純粋関数: 残量と前回通知状態から今回の通知レベル。テスト容易化のため分離。"""
        if left <= crit_at:
            return None if prev == "crit" else "crit"
        if left <= warn_at:
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
            cfg = settings.load()
            warn_at, crit_at = cfg["warn_at"], cfg["crit_at"]
            if left > warn_at + 5:
                self.notified.pop(name, None)
                continue
            level = self.alert_for(left, self.notified.get(name), warn_at, crit_at)
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

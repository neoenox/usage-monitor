# usage-monitor

Codex と Claude Code の使用量スナップショット (Windows / Python 3.11 / 依存ゼロ except GUI)。

## セットアップ（1から連携させる場合）

前提: Codex は ChatGPT Plus/Pro 等、Claude Code は Claude Pro/Max 等のサブスクが必要。

```powershell
# 1. Codex CLI を入れてログイン (初回起動で認証フロー)
npm install -g @openai/codex
codex login
codex  # 一度起動して終了 (セッション履歴 ~/.codex/sessions が作られる)

# 2. Claude Code を入れてログイン
npm install -g @anthropic-ai/claude-code
claude auth login   # ブラウザ連携。資格情報は ~/.claude/.credentials.json に保存
claude auth status  # {"loggedIn": true} を確認

# 3. モニターは何も設定不要
python monitor.py   # Codex: ローカル履歴 / Claude: ログイン資格情報で使用量APIを自動取得
```

補足:

- Claude の使用量 API は `claude auth login` の OAuth をそのまま使う (読取のみ・保存しない)。
  ヘッドレス環境では `claude setup-token` 発行のトークンを環境変数
  `CLAUDE_CODE_OAUTH_TOKEN` か `~/.claude_oauth_token` に置く方法もある。
- Claude の会話履歴 (`~/.claude/projects`) は自動クリーンアップで消えるため、
  トークン集計は参考値。サブスク残量は API 値が正。

## 使い方

```powershell
# CLI
python monitor.py
python monitor.py --json

# GUI
python gui.py
python gui.py --tray   # タスクトレイ常駐 (左クリックで開く)

# テスト
python -m pytest tests -q
```

## 機能

- Codex: 5h/週次 残量バー＋リセット countdown＋枯渇予測、トークン累積、context使用率、推移グラフ
- Claude: サブスク 5h/週次 (`claude auth login` の資格情報を自動読取)、モデル別週次、推移グラフ
- トレイ常駐: ホバー表示、残量20%/10%でバルーン通知、5分毎に自動更新、自動起動ON/OFF

## exe化

```powershell
pip install pyinstaller
python -m PyInstaller --onefile --windowed --name usage-monitor --noconfirm gui.py
```

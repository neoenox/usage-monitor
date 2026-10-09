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

# 3. GUI/トレイ用依存を入れる
python -m pip install -r requirements.txt

# 4. モニターを起動
python monitor.py   # Codex: 公式CLI経由で使用量取得 / Claude: ログイン資格情報で使用量APIを自動取得
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

- Codex: 公式Codexの `account/rateLimits/read` でアカウント全体の5h/週次使用量を取得。DSH・公式アプリ・VS Code拡張・CLIで同じアカウントを使った分を反映（別アカウント・APIキー課金は対象外）。トークン累積・context使用率はローカル履歴の参考値。
  - 公式アプリ同梱CLI／インストール済みCLIを自動検出。認証・トークン更新は公式Codexに任せ、モニターはトークンを読み取らずモデル呼び出しもしない。
  - GUIではCodex・Claudeの前回成功値を `%LOCALAPPDATA%/usage-monitor/last-usage.json` に保存し、通信失敗時・再起動後も残量とバーを維持。「前回取得値」「取得日時」「更新失敗」を明示する。保存するのは使用率・リセット日時のみ（認証情報なし）。
  - リセット後の前回値は「リセット前の参考値」と表示し、100%に置き換えない。前回値から予測・アラート・新しい履歴記録は行わない。未取得なら取得エラーを表示し、復旧後は最新値に戻る。
  - ウィンドウ／トレイの両モードで5分ごとに更新。`CODEX_HOME` にも対応。`--home` で別のHOMEを指定した場合はオフライン履歴のみ読み取る。
- Claude: 公式Claude Codeのstatuslineが出力する5h/週次の使用率・リセット日時だけをローカル保存。資格情報は読み取らず、モニターからモデル呼び出し・OAuth通信は行わない。値はClaude Code利用後に更新され、独立したリアルタイム取得ではない。観測日時付きの参考値として表示する。

## Claude連携の設定・解除

1. 設定タブの「同意してstatusline連携を設定」を選ぶ。保存対象は使用率・リセット日時・観測日時のみ。
2. 既存statuslineがある場合は別途置換の確認を行う。承認しなければ設定を変更しない。承認時は以前のstatuslineをバックアップし、その表示を一時停止する。
3. Claude Codeを再起動して通常利用する。公式statuslineのデータがないプラン・セッションでは未取得になる。使用率取得のためだけにモデルを呼び出さない。
4. 解除・アンインストール前に「以前のstatuslineを復元」を選ぶ。他の設定は維持し、後からユーザーが変更したstatuslineは上書きしない。

配布時の認証条件と制約は [DISTRIBUTION.md](docs/DISTRIBUTION.md) を参照。
- トレイ常駐: ホバー表示、残量20%/10%でバルーン通知、5分毎に自動更新、自動起動ON/OFF

## exe化

ビルドは `build.ps1` の引数指定方式に統一する（アイコン付き）。PyInstallerが生成する `*.spec` はローカル生成物として無視し、Gitには追加しない。

```powershell
pip install pyinstaller
./build.ps1
```

## フォルダー構成

- ルート: 起動用プログラム・設定・ビルド手順
- docs/: 配布条件・検証記録・ロールバック記録
- tests/: テスト
- assets/: アイコン素材
- outputs/: 作業記録（screenshots / backups / diagnostics / reviews）
- build/: ビルド中間ファイル
- dist/: 起動用exe

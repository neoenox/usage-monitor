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
python gui.py   # 設定タブでClaudeのstatusline連携を設定
```

補足:

- Claudeの使用率は公式Claude Codeのstatuslineから受け取ります。モニターはClaudeの認証情報を読み取らず、OAuth更新や使用量APIへの通信を行いません。
- 最初に設定タブでstatusline連携を設定し、Claude Codeを再起動して通常利用してください。使用率はセッションの最初のAPI応答後に届きます。
- 更新はClaude Code利用時のみです。モニター単独でのリアルタイム取得ではありません。観測日時を明示し、期限を過ぎた値はリセット前の参考値として表示します。
- 会話履歴のトークン集計は参考値です。使用枠の割合と区別してください。

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

## 平均使用率とペース配分

5時間枠は時間あたり、週間枠は日あたりの平均使用率と利用目安を表示します。
利用目安は「残りの利用枠 ÷ リセットまでの残り時間」で計算します。
例えば残り60%・残り3時間なら、利用目安は20.0% / 時間までです。
観測された平均が目安以内なら「目安内」、超えていれば「目安超過」と表示します。
目安は小数第1位まで切り捨て、毎分更新します。これは現在の残量・リセット時刻に基づく配分目安です。
平均は同じ利用枠の連続した履歴が10分以上必要ですが、利用目安は履歴不足でも表示できます。
通信失敗時の前回取得値やリセット後の取得待ちから、新しい利用目安は計算しません。Claudeのstatusline観測値では、観測日時を基準にした平均と「観測時の利用目安」を表示します。同じ観測値を何度読み込んでも新しい履歴にしません。

## フォルダー構成

- ルート: 起動用プログラム・設定・ビルド手順
- docs/: 配布条件・検証記録・ロールバック記録
- tests/: テスト
- assets/: アイコン素材
- outputs/: 作業記録（screenshots / backups / diagnostics / reviews）
- build/: ビルド中間ファイル
- dist/: 起動用exe

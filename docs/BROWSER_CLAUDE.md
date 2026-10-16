# Claudeブラウザ連携（Windows / Chrome、日本語表示）

デスクトップ版を普段使う場合も、同じClaudeアカウントのWeb版「設定 → 使用量」から使用率を取り込みます。認証はChromeが管理します。ログインが切れた場合の再ログインは必要です。毎日の再認証が不要になる保証や、数日間の連続動作確認はまだありません。

## 動作

- 拡張が専用の固定タブをバックグラウンドで開き、5分ごとに使用状況ページを再読み込みします。Chromeを閉じている間は取得できません。
- 使用率とリセット時刻の数値だけを、このPCの受信プログラムへ渡します。Cookie・資格情報・会話は取得、保存しません。外部送信もありません。
- Usage Monitorは取り込みファイルを1分ごとに確認します。通常、表示まで最大約6分です。「最新情報に更新」で即時読み込みできます。
- 対応する表示は現在の日本語ページのみ。画面変更、ログアウト、数値が読めない場合は前回の取得日時付きデータを保持します。
- 設定したタブを別ページへ移動した場合、そのページを勝手に再読み込みしません。拡張アイコンをクリックすると新しい専用タブを作ります。
- ブラウザ連携とClaude Code連携が両方ある場合は、取得日時の新しい方を表示します。

## 初回設定

Chrome拡張の追加とローカル連携の登録はユーザーの承認後に実施してください。

1. 同じClaudeアカウントでChromeにログインします。
2. `chrome://extensions` でデベロッパーモードを有効にし、「パッケージ化されていない拡張機能を読み込む」からリポジトリの `browser-extension` フォルダーを選びます。
3. `browser-extension/extension-id.txt` のIDを確認し、ビルドした `dist/usage-monitor-browser-host.exe --register <ID>` を一度実行します。登録先は現在のWindowsユーザーのChrome NativeMessagingHostsのみです。
4. 専用タブを再読み込みし、拡張アイコンが「OK」になったことを確認します。
5. Usage Monitorで更新し、使用率、リセット時刻、ブラウザ由来の取得日時が一致することを確認します。

拡張のアクセス先は `claude.ai/new*` と `claude.ai/settings/usage*`、権限はローカルプログラム通信・定期実行・拡張の設定保存です。ChromeのURL権限はパス単位に制限できないため、ホスト権限はClaudeサイトへのアクセスとして扱われる場合があります。スクリプト側では使用状況ルート以外を処理しません。

## ビルドと解除

受信プログラムは `python -m PyInstaller --onefile --console --name usage-monitor-browser-host claude_browser.py` でビルドします。標準入出力はChromeのnative messaging形式です。通信仕様は[Chrome公式ドキュメント](https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging)に従います。

解除はChromeの拡張機能画面からこの拡張を削除します。必要なら現在ユーザーの `Software\Google\Chrome\NativeMessagingHosts\com.neoenox.usage_monitor` 登録キーだけを削除します。Claudeの認証設定を変更する必要はありません。

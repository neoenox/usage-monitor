# usage-monitor

Codex と Claude Code の使用量スナップショット (Windows / Python 3.11 / 依存ゼロ except GUI)。

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

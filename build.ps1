# exe再ビルド用 (アイコン付き)。usage-monitor/ で実行。
python -m PyInstaller --onefile --windowed --name usage-monitor `
  --icon assets/app.ico --noconfirm gui.py

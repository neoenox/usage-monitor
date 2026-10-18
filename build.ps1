# exe再ビルド用 (アイコン付き・バージョンリソース付き)。usage-monitor/ で実行。
$versionFile = "build/version-info.txt"
New-Item -ItemType Directory -Force -Path build | Out-Null

python windows_version.py --out $versionFile --filename usage-monitor.exe
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python -m PyInstaller --onefile --windowed --name usage-monitor `
  --icon assets/app.ico --add-data "assets/app.ico;assets" --version-file $versionFile --noconfirm gui.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

python windows_version.py --out $versionFile --filename usage-monitor-browser-host.exe
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python -m PyInstaller --onefile --console --name usage-monitor-browser-host `
  --version-file $versionFile --noconfirm claude_browser.py

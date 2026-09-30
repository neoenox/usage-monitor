#!/usr/bin/env python3
"""タスクトレイ/exe用アプリアイコン生成 (Pillow)。紺地に緑ゲージ।"""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent / "app.ico"
S = 256

img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle([8, 8, S - 8, S - 8], radius=52, fill=(17, 24, 39, 255))
# ゲージ弧 (残量75%のイメージ)
d.arc([44, 44, S - 44, S - 44], start=-90, end=180, fill=(34, 197, 94, 255), width=26)
d.arc([44, 44, S - 44, S - 44], start=180, end=270, fill=(55, 65, 81, 255), width=26)
# 中央ドット (Claude青)
d.ellipse([S // 2 - 22, S // 2 - 22, S // 2 + 22, S // 2 + 22], fill=(59, 130, 246, 255))
img.save(OUT, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("wrote", OUT, OUT.stat().st_size, "bytes")

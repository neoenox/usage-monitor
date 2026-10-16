#!/usr/bin/env python3
"""タスクトレイ/exe用アプリアイコン生成 (Pillow)。紺地に地球ブランド。"""
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
SRC = HERE / "brand.png"
OUT = HERE / "app.ico"
S = 256

img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle([8, 8, S - 8, S - 8], radius=52, fill=(17, 24, 39, 255))
globe = Image.open(SRC).convert("RGBA")
inner = S - 52
globe.thumbnail((inner, inner), Image.LANCZOS)
img.paste(globe, ((S - globe.width) // 2, (S - globe.height) // 2), globe)
img.save(OUT, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("wrote", OUT, OUT.stat().st_size, "bytes")

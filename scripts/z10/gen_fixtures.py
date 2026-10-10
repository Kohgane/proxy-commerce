"""BLACKHOLES·플리츠 모양 사진 픽스처(디스크). BLACKHOLES = 타오바오 원본 갤러리 5장(4,160px JPEG 4 + PNG 1 — 크기 꼬리 없음).
플리츠 = 크기 꼬리 있는 갤러리 3장(800px) + 상세 webp 1장(1200px q30)."""
import os, sys
from PIL import Image, ImageFilter
out = sys.argv[1]
def photo(w, h, seed, mode="RGB"):
    n = Image.effect_noise((w // 4, h // 4), 64).resize((w, h)).filter(ImageFilter.GaussianBlur(1))
    g = Image.linear_gradient("L").resize((w, h))
    rgb = Image.merge("RGB", (n, g, Image.eval(n, lambda v: (v * seed) % 256)))
    if mode == "RGBA":
        rgb = rgb.convert("RGBA"); rgb.putalpha(g)
    return rgb
for i in range(4):
    photo(4160, 4160, i + 3).save(f"{out}/bh_{i}.jpg", "JPEG", quality=92)
photo(2400, 2400, 7, "RGBA").save(f"{out}/bh_4.png", "PNG")
for i in range(3):
    photo(800, 800, i + 2).save(f"{out}/pl_{i}.jpg", "JPEG", quality=85)
photo(1200, 1200, 5).save(f"{out}/pl_d.webp", "WEBP", quality=30)
for f in sorted(os.listdir(out)):
    print(f, os.path.getsize(os.path.join(out, f)))

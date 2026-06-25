#!/usr/bin/env python3
"""v23: 고가브릿지 마스터 아이콘 전면 적용 — 단일 소스 한 장에서 전 surface 파생.

확정 마스터 `assets/brand-icons/icon-master-1024.png`(현수교 + 게이트웨이 아치 + 주황
키스톤, 먹/금/청록)에서 favicon/PWA/확장/스토어 전 사이즈를 파생한다. favicon.svg는
마스터 래스터를 임베드(스케일러블 선언 유지). favicon.ico는 16/32/48 멀티사이즈. 지구본/구마크 폐기.
"""
from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "assets" / "brand-icons"
MASTER = SRC / "icon-master-1024.png"
SELLER_STATIC = ROOT / "src" / "seller_console" / "static"
EXT_ICONS = ROOT / "extensions" / "chrome-collector" / "icons"


def _derive(master: Image.Image, size: int) -> Image.Image:
    return master.resize((size, size), Image.LANCZOS)


def _png_bytes(img: Image.Image) -> bytes:
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def main() -> None:
    master = Image.open(MASTER).convert("RGBA")

    # 파생 PNG 세트(단일 소스 → 전 사이즈)
    derived = {n: _derive(master, n) for n in (16, 32, 48, 120, 128, 152, 180, 192, 512, 1024)}
    for n, im in derived.items():
        im.save(SRC / f"icon-{n}.png")                      # repo 벤더 세트도 마스터 기준 동기화

    # 사이트(셀러 정적) 래스터
    derived[192].save(SELLER_STATIC / "icon-192.png")        # PWA
    derived[512].save(SELLER_STATIC / "icon-512.png")        # PWA maskable / Play / OG
    derived[1024].save(SELLER_STATIC / "icon-1024.png")      # App Store
    derived[180].save(SELLER_STATIC / "apple-touch-icon.png")
    derived[16].save(SELLER_STATIC / "favicon-16.png")
    derived[32].save(SELLER_STATIC / "favicon-32.png")
    # favicon.ico — 16/32/48 멀티사이즈(탭/북마크 선명도)
    derived[48].save(SELLER_STATIC / "favicon.ico", format="ICO", sizes=[(16, 16), (32, 32), (48, 48)])

    # favicon.svg — 마스터 래스터(128px) 임베드, 스케일러블 선언 유지(브리지 게이트웨이 마크).
    # 탭/북마크는 16~32px 렌더라 128px면 충분하고 경량(<15KB).
    b64 = base64.b64encode(_png_bytes(derived[128])).decode("ascii")
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512" '
        'role="img" aria-label="Goga Bridj bridge gateway mark">\n'
        f'  <image width="512" height="512" href="data:image/png;base64,{b64}"/>\n'
        '</svg>\n'
    )
    (SELLER_STATIC / "favicon.svg").write_text(svg, encoding="utf-8")

    # 크롬 확장 툴바
    for px in (16, 32, 48, 128):
        derived[px].save(EXT_ICONS / f"{px}.png")

    print("v23 마스터 아이콘 적용 완료: favicon.svg(임베드)/ico, favicon-16/32.png, "
          "apple-touch-icon.png, icon-192/512/1024.png, 확장 16/32/48/128.png (단일소스: icon-master-1024.png)")


if __name__ == "__main__":
    main()

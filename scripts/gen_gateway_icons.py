#!/usr/bin/env python3
"""v21/v22: 고가브릿지 게이트웨이(B) 브랜드 아이콘 적용 — 공식 자산 단일소스.

오너 제공 공식 아이콘 세트(`assets/brand-icons/`, 게이트웨이 아치 + 청록 다리 +
주황 키스톤, 먹/금 vault)를 favicon/PWA/확장/스토어 경로에 적용한다. 직접 그리지 않고
공식 PNG를 그대로 배치(정직·재현 가능). favicon.ico는 공식 16/32/48 PNG로 멀티사이즈 합성.
글러브/지구본 폐기.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "assets" / "brand-icons"                       # 공식 자산 단일소스
SELLER_STATIC = ROOT / "src" / "seller_console" / "static"
EXT_ICONS = ROOT / "extensions" / "chrome-collector" / "icons"


def main() -> None:
    # 사이트(셀러 정적): 벡터 + 래스터
    shutil.copyfile(SRC / "gogabridge_icon_B_gateway.svg", SELLER_STATIC / "favicon.svg")
    shutil.copyfile(SRC / "icon-192.png", SELLER_STATIC / "icon-192.png")
    shutil.copyfile(SRC / "icon-512.png", SELLER_STATIC / "icon-512.png")   # Play / PWA maskable
    shutil.copyfile(SRC / "icon-1024.png", SELLER_STATIC / "icon-1024.png")  # App Store
    shutil.copyfile(SRC / "icon-180.png", SELLER_STATIC / "apple-touch-icon.png")

    # favicon.ico — 공식 16/32/48 PNG로 멀티사이즈 합성(탭/북마크 선명도)
    Image.open(SRC / "icon-48.png").convert("RGBA").save(
        SELLER_STATIC / "favicon.ico", format="ICO", sizes=[(16, 16), (32, 32), (48, 48)]
    )

    # 크롬 확장 툴바
    for px in (16, 32, 48, 128):
        shutil.copyfile(SRC / f"icon-{px}.png", EXT_ICONS / f"{px}.png")

    print("게이트웨이(B) 아이콘 적용 완료: favicon.svg/ico, apple-touch-icon.png, "
          "icon-192/512/1024.png, 확장 16/32/48/128.png (공식 자산: assets/brand-icons)")


if __name__ == "__main__":
    main()

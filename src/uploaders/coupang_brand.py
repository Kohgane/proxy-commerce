"""Y6-B(오너 결정 2026-10-05 · 적용 2026-10-07): 쿠팡 등록 몸통의 `brand` 칸 — GENERIC 규칙.

쿠팡 실측(볼트 2026-10-04 세션로그): `"brand": ""`로 **올리기는 통과**하지만 그 뒤 수정이 전부
「brandId 입력이 필요합니다 … 브랜드가 없는 상품은 brand 필드에 GENERIC을 입력해 주세요」로 막혔다.

규칙(신규 업로드부터 · 기존 등록분 소급 없음):
- 브랜드가 비었거나 / 중국어·비한글 원문이거나 / 쿠팡 브랜드 목록(`coupang_brands.json`) 매칭 실패 → `"GENERIC"`.
- 쿠팡 등록 브랜드로 매칭되면 그 쿠팡 표기.
- `productGroup`·`manufacture`에 넣던 값은 그대로(이 모듈은 `brand` 칸만 정한다).
- 플래그 `COUPANG_BRAND_GENERIC`(기본 0=꺼짐 → 예전 정본 `""`). 1이면 위 규칙(오너 2026-10-07 — Render에 1).
"""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, Tuple

GENERIC = "GENERIC"
ENV_FLAG = "COUPANG_BRAND_GENERIC"
_DEFAULT = Path(__file__).with_name("coupang_brands.json")
_HANGUL = re.compile(r"[가-힣]")
_CJK_KANA = re.compile(r"[぀-ヿ㐀-鿿豈-﫿]")


def _key(s: str) -> str:
    return re.sub(r"[\s._\-·]+", "", str(s or "")).lower()


@lru_cache(maxsize=4)
def _table(path: str) -> Dict[str, str]:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}
    out: Dict[str, str] = {}
    for name, aliases in ((raw or {}).get("brands") or {}).items():
        name = str(name or "").strip()
        if not name or _CJK_KANA.search(name):            # 쿠팡 표기 자체가 한자면 쓰지 않는다
            continue
        for a in [name] + [str(x) for x in (aliases or [])]:
            if _key(a):
                out[_key(a)] = name
    return out


def table() -> Dict[str, str]:
    return _table(os.getenv("COUPANG_BRAND_TABLE", "").strip() or str(_DEFAULT))


def coupang_brand(brand: str) -> Tuple[str, str]:
    """`(쿠팡 brand 칸 값, 사유)`."""
    b = str(brand or "").strip()
    if not b:
        return GENERIC, "브랜드 없음"
    hit = table().get(_key(b))
    if hit:
        return hit, "쿠팡 브랜드 목록 매칭"
    if _CJK_KANA.search(b) or not (_HANGUL.search(b) or re.search(r"[A-Za-z]", b)):
        return GENERIC, "중국어·비한글 원문"
    return GENERIC, "쿠팡 브랜드 목록에 없음"


def enabled() -> bool:
    """`COUPANG_BRAND_GENERIC=1`일 때만 GENERIC 규칙. 기본(0·미설정) = 예전 정본 `brand=""`."""
    return os.getenv(ENV_FLAG, "0").strip() == "1"


def brand_field(brand: str) -> str:
    """등록 몸통 `brand` 칸 값 — 플래그가 꺼져 있으면 `""`(5,691건이 통과한 예전 정본)."""
    return coupang_brand(brand)[0] if enabled() else ""

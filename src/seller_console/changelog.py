"""src/seller_console/changelog.py — v81 STEP7: 변경 가시성(체인지로그 + 콘솔 배너 단일 소스).

배치 버전별 3줄 요약을 **자동 누적**한다(새 배치는 리스트 맨 앞에 dict 하나 추가). 콘솔 상단 배너와
`/seller/changelog` 페이지가 이 단일 소스를 읽는다. 사용자 언어로(시스템 용어·개발 표기 금지, 정직).

각 항목: {version, date, title, lines:[≤3]}. 최신이 맨 앞.
"""
from __future__ import annotations

from typing import Dict, List

# 최신이 맨 앞(prepend). 3줄 요약 = 사용자 눈높이(무엇이 좋아졌나).
CHANGELOG: List[Dict] = [
    {
        "version": "v81",
        "date": "2026-07-22",
        "title": "수집 정직화·소싱처 판정 통일",
        "lines": [
            "간이 수집(제목·이미지만)일 때 ‘간이’로 정직하게 표시하고, ‘다시 수집’으로 상세·가격을 채울 수 있어요.",
            "라쿠텐·아마존 각국 사이트에서 수집 버튼 판정이 팝업과 항상 일치하고, 톱페이지의 추천·최근 본 상품은 수집하지 않아요.",
            "상품명 끝에 붙던 판매처 이름(예: | YOSHIDA & Co.)을 저장 전에 자동으로 정리해요.",
        ],
    },
    {
        "version": "v80",
        "date": "2026-07-21",
        "title": "선택 버튼·알리 목록 안정화",
        "lines": [
            "목록에서 상품을 고르는 체크 버튼이 사이트 배경과 겹쳐도 또렷하게 보여요.",
            "알리익스프레스 카드에 마우스를 올려 이미지가 넘어가도 수집 버튼이 사라지지 않아요.",
            "라쿠텐 상세에서 다른 상품 이미지가 섞이던 문제를 바로잡았어요.",
        ],
    },
    {
        "version": "v79",
        "date": "2026-07-20",
        "title": "옵션·이미지 정제",
        "lines": [
            "옵션 값에 화살표·원산지·브랜드 같은 군더더기가 섞이지 않아요.",
            "대표 이미지에 배너·다른 상품 사진이 끼어드는 걸 걸러내요.",
            "아마존 리뷰의 작성자와 본문을 정확히 구분해 담아요.",
        ],
    },
    {
        "version": "v78",
        "date": "2026-07-19",
        "title": "상세설명·리뷰 품질",
        "lines": [
            "상세설명이 광고 문구 대신 실제 상품 설명으로 채워져요.",
            "리뷰 수·평점이 실제 값으로 반영돼요.",
            "여러 소싱처에서 같은 수준으로 정보를 가져와요.",
        ],
    },
    {
        "version": "v77",
        "date": "2026-07-18",
        "title": "수집 버튼 단일화",
        "lines": [
            "사이트가 화면을 바꿔도 수집 버튼이 깜빡이거나 사라지지 않아요.",
            "목록·상세 어디서나 같은 방식으로 버튼이 떠요.",
            "버튼 위치·모양을 하나의 규칙으로 통일했어요.",
        ],
    },
]


def get_changelog() -> List[Dict]:
    """전체 체인지로그(최신순)."""
    return CHANGELOG


def latest() -> Dict:
    """가장 최신 배치 항목(배너용). 비어 있으면 빈 dict."""
    return CHANGELOG[0] if CHANGELOG else {}


def banner_summary() -> Dict:
    """콘솔 배너용 요약 — {version, title, items:[≤2 짧은 항목]}."""
    top = latest()
    if not top:
        return {}
    lines = list(top.get("lines") or [])
    # 배너는 앞 두 줄의 '핵심 명사구'만 짧게(전문은 페이지에서).
    points = []
    for ln in lines[:2]:
        head = ln.split(".")[0].split(",")[0].strip()
        points.append(head[:34])
    # 'items' 키는 Jinja에서 dict.items()와 충돌 → 'points'로.
    return {"version": top.get("version", ""), "title": top.get("title", ""), "points": points}

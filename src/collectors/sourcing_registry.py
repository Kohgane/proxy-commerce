"""src/collectors/sourcing_registry.py — v70 STEP4: 디폴트 소싱처 레지스트리(명문화·단일 소스).

확장(content_script.js `KGP_DEFAULT_SOURCES`)에 등록된 기본 소싱처를 서버에서도 명문화한다.
콘솔 소싱처 가이드(`/seller/guide/sources`)가 이 표를 렌더하고, 가드 테스트가 확장 레지스트리와
id 일치(드리프트 0)를 강제한다.

버튼 보장 계약(v63 원칙): 레지스트리 사이트는 어댑터 셀렉터가 실패해도 **제네릭 타일 휴리스틱**이
반드시 발동한다. 따라서 (a) 검색/카테고리 목록 → 호버 [수집] + 중앙 벌크바 (b) 상품 상세 → 우측 단건
버튼이 항상 노출된다. 아마존은 정밀 어댑터(`_kgpAmazonCards`)가 제네릭을 보강(정밀), 그 외는 제네릭 단독.
"""
from __future__ import annotations

# id는 확장 KGP_DEFAULT_SOURCES와 1:1(가드 test_v70_default_sites_parity가 강제).
#   list/hover/detail = 버튼 보장 지원 여부(전 사이트 지원 — 제네릭 휴리스틱이 폴백으로 항상 발동).
#   adapter = 정밀 사이트 어댑터 유무(제네릭 위 보강). 미지원 항목은 note에 정직 표기(현재 없음).
DEFAULT_SOURCING_SITES = [
    {"id": "taobao", "label": "타오바오", "domains": "taobao.com", "adapter": False},
    {"id": "tmall", "label": "티몰", "domains": "tmall.com", "adapter": False},
    {"id": "1688", "label": "1688", "domains": "1688.com", "adapter": False},
    {"id": "temu", "label": "테무", "domains": "temu.com", "adapter": False,
     "note": "SPA — 상세 렌더 보강(소형 창) 경유"},
    {"id": "amazon", "label": "아마존", "domains": "amazon.com · amazon.co.jp 등", "adapter": True,
     "note": "정밀 어댑터(검색결과 카드·ASIN)"},
    {"id": "aliexpress", "label": "알리익스프레스", "domains": "aliexpress.com · aliexpress.us", "adapter": False},
    {"id": "iherb", "label": "아이허브", "domains": "iherb.com", "adapter": False},
    {"id": "dhgate", "label": "DHgate", "domains": "dhgate.com", "adapter": False},
    {"id": "qoo10", "label": "큐텐", "domains": "qoo10.*", "adapter": False},
    {"id": "mercari", "label": "메루카리", "domains": "mercari.com", "adapter": False},
    {"id": "rakuten", "label": "라쿠텐", "domains": "rakuten.co.jp · rakuten.com", "adapter": False},
    {"id": "yahoo", "label": "야후쇼핑(재팬)", "domains": "shopping.yahoo.co.jp · paypaymall.yahoo.co.jp", "adapter": False},
    {"id": "yoshida", "label": "요시다카반", "domains": "yoshidakaban.com", "adapter": False},
]


def registry_ids():
    """레지스트리 id 목록(확장과 일치해야 함)."""
    return [s["id"] for s in DEFAULT_SOURCING_SITES]


def registry_rows():
    """가이드 템플릿용 행(버튼 보장 지원 3열 + 비고). 전 사이트 목록/호버/상세 지원."""
    rows = []
    for s in DEFAULT_SOURCING_SITES:
        rows.append({
            "id": s["id"],
            "label": s["label"],
            "domains": s["domains"],
            "list_btn": True,     # 목록: 중앙 벌크바 + 카드 배지(제네릭 휴리스틱 보장)
            "hover": True,        # 호버: 썸네일 [수집] 알약
            "detail_btn": True,   # 상세: 우측 단건 FAB
            "adapter": bool(s.get("adapter")),
            "note": s.get("note", ""),
        })
    return rows

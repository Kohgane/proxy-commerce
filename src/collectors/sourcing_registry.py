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
#
# v75 STEP1: coverage = **추출 커버리지**(제목·가격·갤러리·옵션·상세·리뷰) — 근거는 실페이지 하네스
#   픽스처(fixtures/realpages/<fixture>.expected.json)의 실제 어서션뿐(추측 기입 금지). fixture 없으면
#   level='unverified' + needs_snapshot=True(오너 스냅샷 요청). 가드 test_v75_coverage_matrix가 claim한
#   fixture·필드가 실제 expected.json에 있는지 강제 → '진단 없는 지원' 표기 차단.
#   fields = 하네스가 검증한 필드, unverified = 미검증(픽스처 있어도 미어서션) 필드.
DEFAULT_SOURCING_SITES = [
    {"id": "taobao", "label": "타오바오", "domains": "taobao.com", "adapter": False,
     "coverage": {"level": "unverified", "needs_snapshot": True}},
    {"id": "tmall", "label": "티몰", "domains": "tmall.com", "adapter": False,
     "coverage": {"level": "unverified", "needs_snapshot": True}},
    {"id": "1688", "label": "1688", "domains": "1688.com", "adapter": False,
     "coverage": {"level": "unverified", "needs_snapshot": True}},
    {"id": "temu", "label": "테무", "domains": "temu.com", "adapter": False,
     "note": "SPA — 상세 렌더 보강(소형 창) 경유",
     "coverage": {"level": "full", "fixture": "synthetic-temu-detail",
                  "fields": ["title", "price", "currency", "gallery", "options", "description"],
                  "unverified": ["reviews"]}},
    {"id": "amazon", "label": "아마존", "domains": "amazon.com · amazon.co.jp 등", "adapter": True,
     "note": "정밀 어댑터(검색결과 카드·ASIN)",
     "coverage": {"level": "full", "fixture": "synthetic-amazon-dp",
                  "fields": ["title", "price", "currency", "gallery", "options", "description"],
                  "unverified": ["reviews"]}},
    {"id": "aliexpress", "label": "알리익스프레스", "domains": "aliexpress.com · aliexpress.us", "adapter": False,
     "coverage": {"level": "partial", "fixture": "ali-detail",
                  "fields": ["title", "price", "currency", "gallery", "options"],
                  "unverified": ["description", "reviews"]}},
    {"id": "iherb", "label": "아이허브", "domains": "iherb.com", "adapter": False,
     "coverage": {"level": "unverified", "needs_snapshot": True}},
    {"id": "dhgate", "label": "DHgate", "domains": "dhgate.com", "adapter": False,
     "coverage": {"level": "unverified", "needs_snapshot": True}},
    {"id": "qoo10", "label": "큐텐", "domains": "qoo10.*", "adapter": False,
     "coverage": {"level": "unverified", "needs_snapshot": True}},
    {"id": "mercari", "label": "메루카리", "domains": "mercari.com", "adapter": False,
     "coverage": {"level": "unverified", "needs_snapshot": True}},
    {"id": "rakuten", "label": "라쿠텐", "domains": "rakuten.co.jp · rakuten.com", "adapter": False,
     "coverage": {"level": "unverified", "needs_snapshot": True}},
    {"id": "yahoo", "label": "야후쇼핑(재팬)", "domains": "shopping.yahoo.co.jp · paypaymall.yahoo.co.jp", "adapter": False,
     "coverage": {"level": "unverified", "needs_snapshot": True}},
    {"id": "yoshida", "label": "요시다카반", "domains": "yoshidakaban.com", "adapter": False,
     "note": "목록 버튼 하네스 검증(yoshida-list) — 상세 추출은 스냅샷 필요",
     "coverage": {"level": "unverified", "needs_snapshot": True}},
]


def registry_ids():
    """레지스트리 id 목록(확장과 일치해야 함)."""
    return [s["id"] for s in DEFAULT_SOURCING_SITES]


_ALL_EXTRACT_FIELDS = ["title", "price", "currency", "gallery", "options", "description", "reviews"]


def _coverage_badge(cov):
    """지원 수준 배지(완전/부분/미검증) + 누락 필드 안내 — '진단 없는 지원' 표기 차단."""
    cov = cov or {}
    level = cov.get("level", "unverified")
    fields = cov.get("fields") or []
    unver = cov.get("unverified") or []
    if level == "full":
        return {"level": "full", "label": "완전 지원", "css": "success",
                "detail": "제목·가격·갤러리·옵션·상세 하네스 검증"
                + (" (리뷰 미검증)" if "reviews" in unver else ""),
                "fixture": cov.get("fixture", "")}
    if level == "partial":
        miss = [f for f in _ALL_EXTRACT_FIELDS if f not in fields]
        return {"level": "partial", "label": "부분 지원", "css": "warning",
                "detail": "검증: " + "·".join(fields) + " / 미검증: " + "·".join(miss),
                "fixture": cov.get("fixture", "")}
    return {"level": "unverified", "label": "미검증", "css": "secondary",
            "detail": "실페이지 스냅샷 필요(오너 제출 후 하네스 검증)", "fixture": ""}


def registry_rows():
    """가이드 템플릿용 행(버튼 보장 3열 + 추출 커버리지 배지 + 비고)."""
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
            "coverage": _coverage_badge(s.get("coverage")),   # v75 STEP1: 추출 지원 수준 배지
        })
    return rows


def snapshot_needed():
    """오너 스냅샷 요청 목록 — coverage=unverified(픽스처 미보유) 마켓."""
    return [{"id": s["id"], "label": s["label"], "domains": s["domains"]}
            for s in DEFAULT_SOURCING_SITES
            if (s.get("coverage") or {}).get("level", "unverified") == "unverified"]


def coverage_matrix_rows():
    """9항목 매트릭스 행 — 버튼 3(전부 보장) + 추출 6(하네스 검증분만 ✓, 그 외 '픽스처 필요')."""
    rows = []
    for s in DEFAULT_SOURCING_SITES:
        cov = s.get("coverage") or {}
        fields = set(cov.get("fields") or [])
        def mark(f):
            if f in fields:
                return "✓"
            if cov.get("level") == "unverified":
                return "픽스처 필요"
            return "미검증"
        price_cell = "✓" if ("price" in fields and "currency" in fields) else mark("price")
        rows.append({
            "id": s["id"], "label": s["label"], "domains": s["domains"],
            "list_btn": "✓", "hover": "✓", "detail_btn": "✓",   # 제네릭 버튼 보장(전 사이트)
            "title": mark("title"), "price": price_cell,
            "gallery": mark("gallery"), "options": mark("options"),
            "description": mark("description"), "reviews": mark("reviews"),
            "level": cov.get("level", "unverified"), "fixture": cov.get("fixture", ""),
        })
    return rows

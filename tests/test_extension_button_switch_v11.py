"""tests/test_extension_button_switch_v11.py — v11 P0 버튼 자동 전환 가드(정적).

목록=중앙 바만 / 상세=우측 FAB만(동시 노출 0) 로직과 단일 아이콘 잔재 제거를 핀으로 고정.
"""
from __future__ import annotations

from pathlib import Path

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")


def test_detail_vs_list_helpers_exist():
    assert "function kgpIsDetailUrl" in CS
    assert "function kgpRemoveFab" in CS
    assert "function kgpRemoveListing" in CS


def test_detail_url_patterns():
    for pat in ["/dp/", "gp/product", "item.htm", "offer/detail", "g-?", "/product/"]:
        assert pat in CS, f"상세 URL 패턴 {pat} 누락"


def test_mutual_exclusion_in_refresh():
    # kgpRefresh가 목록이면 FAB 제거, 상세면 리스팅 제거(동시 노출 0).
    assert "const isList = cards.length >= 3" in CS
    assert "kgpRemoveFab();" in CS
    assert "kgpRemoveListing();" in CS
    # v38 #4: FAB는 더 이상 상품 페이지 휴리스틱으로 막지 않음(소싱처면 항상 노출).
    #         host 게이트만 유지(소싱처/앱 진입 한정).
    assert "if (!looksLikeProductPage() && !kgpIsDetailUrl()) return;" not in CS
    assert "if (!kgpHostAllowed() && !kgpEntrySession()) return;" in CS


def test_bookmarklet_button_no_emoji_no_globe():
    bm = Path("src/seller_console/templates/bookmarklet.html").read_text(encoding="utf-8")
    # 파일 가져오기 방식(ICON 속성)으로 전환 — 드래그 앵커(지구본 경로) 폐기.
    assert "draggable" not in bm and "bmDragZone" not in bm and "issueAndBuild" not in bm
    assert "내 북마클릿 파일 받기" in bm          # 파일 받기 CTA
    assert "🧤" not in bm and "globe" not in bm.lower()

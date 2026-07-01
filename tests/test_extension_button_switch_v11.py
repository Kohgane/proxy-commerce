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
    # v40 B: 드래그 앵커는 '글자 0'(텍스트 노드 없음·아이콘 CSS background). '고가수집기' 라벨은 앵커 밖 형제.
    assert "></a>" in bm                         # 앵커 내부 텍스트 노드 0
    assert ">고가수집기</a>" not in bm            # 옛 텍스트-인-앵커 폐기
    assert 'aria-label="고가수집기"' in bm        # a11y 이름은 aria-label로만
    assert "🧤" not in bm and "globe" not in bm.lower()
    assert "filename='favicon.svg'" not in bm and 'filename="favicon.svg"' not in bm

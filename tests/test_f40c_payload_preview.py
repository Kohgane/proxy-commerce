"""F40-c 계약 — 미리보기가 **등록이 보낼 바로 그 값**을 보여 준다.

## 왜 이 화면이 생겼나 (오너 2026-09-21)

같은 증상(`뽑힌 값: ''`)을 **네 번** 고쳤다. 매번 로그로 되짚는 동안 카나리가 멈춰 있었다.

> 라이브 build 697c9ef에서 수행방패가 **여전히 `''`** — 이 화면이 좌표를 준다.

## ★★★ 그 좌표가 실제로 나왔다

주소는 F40-b로 채워졌는데 **`sku` 키를 아무도 안 만들고 있었다.**
쿠팡 업로더는 `product['sku']`를 읽고, 서랍의 `buildProductData()`엔 그 키가 없다.
`vendor_sku(draft_url(...))`를 하는 자리는 **파일럿(멀티샵) 한 곳뿐**이었다.

| 트랙 | 무엇을 고쳤나 |
|---|---|
| F39 | 주소의 **이름**(`source_url` vs `url`) |
| F40 | 주소의 **출처**(행 컬럼 vs extra) |
| F40-b | 주소의 **경로**(단건·일괄·재등록) |
| **F40-c** | **주소에서 번호를 뽑는 자리가 비어 있었다** |

## 오너가 못박은 계약

> **미리보기의 sku == 실제 dispatch가 보내는 sku (같은 함수).**

미리보기가 다른 계산을 하면 **그건 거짓말**이고, 좌표를 주기는커녕 한 판을 더 태운다.
"""
from __future__ import annotations

import pytest

from src.seller_console.upload_dispatcher import (build_dispatch_payload, draft_url,
                                                  payload_diagnosis)
from tests._ast_probe import calls_in

TMALL = "https://detail.tmall.com/item.htm?id=617129397971"
SHARE = "https://e.tb.cn/h.abc?tk=XYZ"
ROW = {"url": TMALL}


# ---------------------------------------------------------------------------
# ★★★ 오너 계약 — 미리보기 == 실제
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("pd,item", [
    ({"title": "수행방패"}, ROW),
    ({"url": TMALL}, None),
    ({"url": SHARE}, ROW),
    ({"final_url": TMALL}, None),
    ({"title": "주소 없음"}, None),
    ({"sku": "MANUAL-1", "url": TMALL}, ROW),
])
def test_the_preview_sku_is_the_dispatch_sku(pd, item):
    """★★★ **판정 지점** — 같은 함수를 부르므로 값이 갈릴 수 없다."""
    sent = build_dispatch_payload(pd, item)
    shown = payload_diagnosis(pd, item)
    assert shown["sku"] == str(sent.get("sku") or "")


@pytest.mark.parametrize("pd,item", [
    ({"title": "수행방패"}, ROW),
    ({"url": SHARE}, ROW),
    ({"title": "주소 없음"}, None),
])
def test_the_preview_url_is_the_dispatch_url(pd, item):
    assert payload_diagnosis(pd, item)["chosen_url"] == draft_url(
        build_dispatch_payload(pd, item))


def test_the_preview_calls_the_real_builder():
    """★★ 같은 **함수**를 부르는지 구조로 확인 — 계산을 베껴 두면 언젠가 갈린다."""
    got = calls_in(payload_diagnosis)
    assert "build_dispatch_payload" in got
    assert "draft_url" in got and "vendor_sku" in got


# ---------------------------------------------------------------------------
# ★★★ F40-c가 찾아낸 근원 — sku 키가 없었다
# ---------------------------------------------------------------------------

def test_the_sku_is_derived_from_the_chosen_url():
    """★★★ **라이브 697c9ef의 근원.** 주소는 있는데 `sku` 키를 아무도 안 만들었다."""
    sent = build_dispatch_payload({"title": "수행방패"}, ROW)
    assert sent["sku"] == "617129397971"


def test_a_seller_typed_sku_wins():
    """★ 셀러가 적어 둔 값은 **우리가 덮지 않는다.**"""
    sent = build_dispatch_payload({"sku": "MANUAL-1", "url": TMALL}, ROW)
    assert sent["sku"] == "MANUAL-1"


def test_no_url_means_no_invented_sku():
    """★★ 주소가 없으면 **지어내지 않는다** — 빈 채로 두고 하류가 정직하게 멈춘다."""
    sent = build_dispatch_payload({"title": "주소 없음"}, None)
    assert "sku" not in sent


def test_a_share_link_alone_yields_no_sku():
    """★ 공유 링크는 주소지만 **상품번호가 없다** — 없는 걸 만들지 않는다."""
    sent = build_dispatch_payload({"url": SHARE}, None)
    assert not sent.get("sku")


# ---------------------------------------------------------------------------
# 화면이 주는 좌표
# ---------------------------------------------------------------------------

def test_every_candidate_is_listed_with_where_it_came_from():
    """★ 「왜 이 주소를 골랐나」가 표에서 풀려야 한다."""
    d = payload_diagnosis({"url": SHARE, "final_url": TMALL}, ROW)
    srcs = " ".join(c["source"] for c in d["candidates"])
    assert "url" in srcs and "final_url" in srcs and "행" in srcs
    used = [c for c in d["candidates"] if c["used"]]
    assert len(used) == 1 and used[0]["sku"] == "617129397971"


def test_non_url_keys_are_shown_but_marked_as_not_candidates():
    """★ 「share_tk는 왜 안 쓰나」 — 보여 주되 **주소 후보가 아니라고** 적는다."""
    d = payload_diagnosis({"share_tk": "XYZ", "url": TMALL}, None)
    tk = [c for c in d["candidates"] if "share_tk" in c["source"]]
    assert tk and "주소 후보 아님" in tk[0]["source"] and tk[0]["used"] is False


def test_the_failure_sentence_is_the_one_registration_would_print():
    """★★ 미리보기가 **다른 문장**을 보여 주면 사람이 엉뚱한 곳을 판다."""
    d = payload_diagnosis({"title": "주소 없음"}, None)
    assert d["sku_ok"] is False
    assert "상품 주소가 페이로드에 없습니다" in d["reason"]
    assert "뽑힌 값: ''" in d["reason"]


def test_it_sends_nothing():
    """★★★ 오너 계약 — **전송 0회.** 진단하러 들어가 등록이 되면 안 된다."""
    assert payload_diagnosis({"url": TMALL}, ROW)["sent"] is False
    assert "dispatch" not in calls_in(payload_diagnosis)


# ---------------------------------------------------------------------------
# 관리자만
# ---------------------------------------------------------------------------

def test_the_route_is_admin_only():
    from src.seller_console import views
    got = calls_in(views.collect_payload_preview)
    assert "_is_admin_user" in got and "_check_auth" in got


def test_the_route_uses_the_shared_diagnosis():
    from src.seller_console import views
    assert "payload_diagnosis" in calls_in(views.collect_payload_preview)


def test_the_button_is_hidden_from_sellers():
    """★ 진단 도구를 일반 셀러에게 보이지 않는다(개발 표기 비노출 원칙)."""
    from pathlib import Path
    html = (Path(__file__).resolve().parents[1] / "src" / "seller_console" /
            "templates" / "collect_preview.html").read_text(encoding="utf-8")
    i = html.index("btnPayloadPreview")
    assert "{% if session.get('user_role') == 'admin' %}" in html[:i]

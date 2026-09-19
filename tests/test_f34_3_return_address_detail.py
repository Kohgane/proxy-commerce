"""F34-3 계약 — 상세주소를 기본주소 칸에 넣지 않는다 (오너 2026-09-19).

후보 사전에 `addressDetail`이 **기본주소**(`COUPANG_RETURN_ADDRESS`) 후보로 들어 있었다.
응답에 `returnAddress`가 없고 `addressDetail`만 있으면 기본주소 칸에 「4층 101호」가 찬다 —
화면에선 그럴듯하고 **쿠팡에 나가는 순간 틀린다**.

> ★ **한 줄에 두 뜻을 담지 않는다.** 보이는 자리에서 맞는 값이 나가는 자리에서 틀리면,
> 그건 값이 아니라 우연이다.

후보 이름은 여전히 **지어내지 않는다** — `returnAddressDetail`은 오너가 준 이름이다.
"""
from __future__ import annotations


def test_address_detail_is_no_longer_a_base_address_candidate():
    """★ **F34-3의 판정 지점.**"""
    from src.seller_console.coupang_shipping_lookup import RETURN_FIELD_CANDIDATES
    assert "addressDetail" not in RETURN_FIELD_CANDIDATES["COUPANG_RETURN_ADDRESS"]


def test_the_detail_field_has_its_own_candidate():
    from src.seller_console.coupang_shipping_lookup import RETURN_FIELD_CANDIDATES
    assert RETURN_FIELD_CANDIDATES["COUPANG_RETURN_ADDRESS_DETAIL"] == ("returnAddressDetail",)


def test_a_detail_only_row_leaves_the_base_address_empty():
    """★★ 기본주소가 없으면 **비워 둔다** — 상세주소로 채우지 않는다.

    비어 있으면 사람이 채운다. 틀린 값이 차 있으면 아무도 안 고친다.
    """
    from src.seller_console import coupang_shipping_lookup as L
    row = {"returnCenterCode": "1002166041", "addressDetail": "4층 101호"}
    mapped = L._map_row(row, L.RETURN_FIELD_CANDIDATES)
    assert mapped.get("COUPANG_RETURN_ADDRESS", "") == "", mapped
    assert mapped["COUPANG_RETURN_CENTER_CODE"] == "1002166041"


def test_the_real_names_still_map():
    """오너가 준 이름은 그대로 각자 칸으로 간다."""
    from src.seller_console import coupang_shipping_lookup as L
    row = {"returnAddress": "경기도 김포시 통진읍 서암리",
           "returnAddressDetail": "4층 101호"}
    mapped = L._map_row(row, L.RETURN_FIELD_CANDIDATES)
    assert mapped["COUPANG_RETURN_ADDRESS"] == "경기도 김포시 통진읍 서암리"
    assert mapped["COUPANG_RETURN_ADDRESS_DETAIL"] == "4층 101호"


def test_the_detail_field_exists_on_the_screen():
    """채울 칸이 화면에 있어야 매핑이 의미가 있다."""
    from src.seller_console.market_credentials import MARKET_CRED_FIELDS
    envs = {f["env"] for f in MARKET_CRED_FIELDS["coupang"]}
    assert "COUPANG_RETURN_ADDRESS_DETAIL" in envs

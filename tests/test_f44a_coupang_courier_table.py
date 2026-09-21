"""F44-a 계약 — 쿠팡 택배사 코드표가 **문서 그대로** 있고, 규격 밖은 안 나간다.

## 정본

쿠팡 개발자센터 「택배사 코드」 **문서 버전 2609170000** — 오너가 2026-09-21 텍스트로 붙여넣고,
취소선(합병·폐업)은 같은 날 **화면 캡처 4장**으로 확정했다.

데이터는 `coupang_courier_codes.py`(표만), 규칙은 `coupang_courier_rules.py`(검색·검증).
**표에 로직을 섞지 않는다** — 다음 개정 때 무엇이 문서고 무엇이 우리 것인지 갈린다.

## 오너가 못박은 계약 넷

| # | 계약 |
|---|---|
| 1 | **코드 수 == 파일 행 수**(중복 0) |
| 2 | **INACTIVE 14** |
| 3 | **카나리 5개 active** (CJGLS EPOST HANJIN HYUNDAI KGB) |
| 4 | **한국어 입력이 코드로 나가는 경로 0** |

## 그리고 지어내지 않는 자리

- **후계 매핑 금지** — `KOREX`(합병)를 `CJGLS`로 바꾸지 않는다. 문서에 그런 말이 없다.
- **자리수 미지정은 검증 생략 + 그렇다고 말한다** — 아무 값이나 맞다고 하지 않는다.
- **「○○와 동일」은 상속** — 숫자를 베껴 두면 원본이 바뀔 때 사본만 낡는다.
"""
from __future__ import annotations

import re

import pytest

from src.seller_console.orders import coupang_courier_rules as RULES
from src.seller_console.orders.coupang_courier_codes import (BY_CODE, CANARY_WHITELIST,
                                                             COUPANG_COURIERS, INACTIVE)


# ---------------------------------------------------------------------------
# 1~3) 오너가 못박은 수치
# ---------------------------------------------------------------------------

def test_no_duplicate_codes():
    """★ 코드 수 == 행 수. 중복이 있으면 **뒤의 행이 앞을 조용히 덮는다.**"""
    assert len(BY_CODE) == len(COUPANG_COURIERS)


def test_exactly_fourteen_are_retired():
    """★★ 취소선 14건 — 캡처로 확정한 수다. 늘거나 줄면 **문서가 바뀐 것**이다."""
    assert len(INACTIVE) == 14
    assert set(INACTIVE) == {
        "KOREX", "HILOGIS", "DNDN", "KGBLS", "KGBPS", "DONGBU", "YELLOW",
        "INNOGIS", "DADREAM", "IQS", "SFEXPRESS", "LGE", "WINION", "WINION2"}


def test_the_canary_five_are_live():
    for code in CANARY_WHITELIST:
        assert BY_CODE[code].active, code


def test_morningglobal_is_not_retired():
    """★ 오너 확인 — 취소선은 **그 아래부터** 연속이다(MORNINGGLOBAL은 현역)."""
    assert BY_CODE["MORNINGGLOBAL"].active is True


# ---------------------------------------------------------------------------
# 문서 오기 정정 · 중복 병합
# ---------------------------------------------------------------------------

def test_the_two_swapped_rows_are_corrected():
    """★ 문서에서 코드/이름 열이 뒤바뀐 2건."""
    assert BY_CODE["GKGLOBAL"].name == "지케이글로벌"
    assert BY_CODE["GKGLOBAL"].lens == (11,)
    assert BY_CODE["GONELO"].name == "고넬로"


def test_goodstoluck_merged_with_the_longer_rule():
    """★ 문서에 두 행(자리수 `-`와 12) → **하나로, 12 채택**(오너 지시)."""
    c = BY_CODE["GOODSTOLUCK"]
    assert c.lens == (12,)
    assert "두 행" in c.note


def test_direct_is_the_unsupported_fallback():
    """★★ F44(b)의 「쿠팡 미지원 택배사」 대체 코드 — **추적 없음**을 말한다."""
    st = RULES.status("DIRECT")
    assert st["active"] and st["tracking"] is False
    assert "트래킹" in st["note"]


# ---------------------------------------------------------------------------
# 「○○와 동일」 = 상속
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("code,parent", [
    ("CVS", "CJGLS"), ("BGF", "CJGLS"), ("REGISTPOST", "EPOST"), ("BANPOOM", "HANJIN")])
def test_same_as_rows_inherit_instead_of_copying(code, parent):
    """★★ 숫자를 베껴 두면 **원본이 바뀔 때 사본만 낡는다**(F34-2 사본 드리프트)."""
    lens, _pattern, _alnum, src = RULES.effective_rule(code)
    assert lens == BY_CODE[parent].lens or lens == BY_CODE[code].lens
    assert src == parent or BY_CODE[code].lens


def test_banpoom_gets_hanjins_lengths_though_its_own_cell_was_blank():
    """★ 자리수 칸이 「한진택배와 동일」이라 비어 있다 — 상속이 그걸 채운다."""
    assert BY_CODE["BANPOOM"].lens is None
    lens, _p, _a, src = RULES.effective_rule("BANPOOM")
    assert lens == BY_CODE["HANJIN"].lens and src == "HANJIN"


# ---------------------------------------------------------------------------
# 4) ★★★ 한국어가 코드로 나가는 경로 0
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", ["CJ대한통운", "한진택배", "우체국", "롯데택배", "경동택배"])
def test_a_korean_name_is_never_accepted_as_a_code(name):
    """★★★ **오너가 못박은 계약** — 이름은 코드가 아니다."""
    from src.seller_console.orders.sync_service import courier_code_hold
    assert courier_code_hold("coupang", name), name


def test_resolving_a_name_to_a_code_is_explicit_not_silent():
    """★★ 이름→코드는 **사람이 고르는 화면**의 일이다. 전송 경로가 몰래 바꾸지 않는다."""
    import inspect

    from src.seller_console.orders import sync_service
    src = inspect.getsource(sync_service.courier_code_hold)
    assert "resolve_name" not in src, "전송 관문이 이름을 코드로 바꾸고 있다"


def test_resolve_name_answers_only_when_certain():
    assert RULES.resolve_name("CJ") == "CJGLS"           # 승인된 별칭
    assert RULES.resolve_name("CJGLS") == "CJGLS"        # 코드 그대로
    assert RULES.resolve_name("CJ대한통운") == "CJGLS"    # 문서 이름 정확일치
    assert RULES.resolve_name("대한") == ""              # 부분일치로는 답하지 않는다
    assert RULES.resolve_name("없는이름") == ""


@pytest.mark.parametrize("alias,code", [
    ("CJ", "CJGLS"), ("대한통운", "CJGLS"), ("롯데", "HYUNDAI"), ("로젠", "KGB"),
    ("우체국", "EPOST"), ("한진", "HANJIN"), ("경동", "KDEXP")])
def test_the_seven_approved_aliases(alias, code):
    """★ 오너가 준 별칭 일곱 — **문서 이름의 통용 축약**이지 발명이 아니다."""
    assert RULES.COUPANG_ALIASES[alias] == code


def test_no_extra_aliases_were_invented():
    assert len(RULES.COUPANG_ALIASES) == 7


# ---------------------------------------------------------------------------
# 검색 — 코드 정확일치 → 이름/별칭 부분일치
# ---------------------------------------------------------------------------

def test_every_code_is_reachable_by_search():
    """★★★ **오너 계약** — 표의 모든 코드가 검색으로 도달 가능."""
    missing = [c.code for c in COUPANG_COURIERS
               if c.code not in {r["code"] for r in RULES.find(c.code, limit=50)}]
    assert not missing, missing


def test_an_exact_code_comes_first():
    """★ 코드를 아는 사람은 그걸 친다 — 부분일치가 위에 오면 자기 코드를 한참 찾는다."""
    rows = RULES.find("KGB")
    assert rows[0]["code"] == "KGB"


def test_a_korean_name_finds_its_code():
    rows = RULES.find("한진")
    assert "HANJIN" in [r["code"] for r in rows]


def test_a_retired_courier_is_shown_but_not_selectable():
    """★★ 숨기면 「내 택배사가 왜 없지」가 된다 — **보이되 고를 수 없다.**"""
    rows = RULES.find("KOREX")
    assert rows and rows[0]["code"] == "KOREX"
    assert rows[0]["selectable"] is False
    assert rows[0]["reason"] == RULES.UNSUPPORTED_LABEL


def test_the_search_result_carries_the_length_rule():
    """★ 오너 지시 — 결과에 **자리수 규칙**을 표시한다."""
    rows = RULES.find("CJGLS")
    assert "10자리" in rows[0]["lens_label"]
    assert RULES.find("GONELO")[0]["lens_label"] == RULES.NO_SPEC_LABEL


# ---------------------------------------------------------------------------
# 검증 — 규격 밖은 전송 0회
# ---------------------------------------------------------------------------

def test_a_wrong_length_is_held_before_sending():
    """★★★ 문서 첫 줄 — 「규격에 맞지 않는 운송장은 에러」. 마켓에서 받느니 여기서 멈춘다."""
    ok, why = RULES.validate("CJGLS", "123")
    assert ok is False and "쿠팡 규격" in why and "10자리" in why


@pytest.mark.parametrize("code,num", [
    ("CJGLS", "1234567890"), ("CJGLS", "680405450931"),
    ("EPOST", "6900004147609"), ("HANJIN", "1547827315"),
    ("HYUNDAI", "200016500003"), ("KGB", "20286005541"),
    ("KDEXP", "1698100690123456"), ("CHUNIL", "21012345678")])
def test_the_documented_examples_pass(code, num):
    """★★ **문서가 준 예시가 통과해야** 검증이 맞는 것이다(우리 규칙이 문서를 이기면 안 된다)."""
    ok, why = RULES.validate(code, num)
    assert ok, (code, num, why)


def test_the_ems_pattern_is_enforced():
    assert RULES.validate("EMS", "RA151630799KR")[0] is True
    assert RULES.validate("EMS", "1234567890123")[0] is False


def test_thebao_pattern_from_the_documented_example():
    assert RULES.validate("THEBAO", "B1CA0120220211000001")[0] is True
    assert RULES.validate("THEBAO", "B2CA0120220211000001")[0] is False


def test_argo_two_letters_then_fourteen_digits():
    assert RULES.validate("ARGO", "AB12345678901234")[0] is True
    assert RULES.validate("ARGO", "ABC2345678901234")[0] is False


def test_an_unspecified_length_skips_validation_and_says_so():
    """★★ 모르면서 막지 않고, 모르면서 맞다고도 하지 않는다."""
    ok, why = RULES.validate("GONELO", "whatever123")
    assert ok is True and why == ""
    assert RULES.status("GONELO")["lens_label"] == RULES.NO_SPEC_LABEL


def test_a_retired_code_is_refused_without_a_successor_guess():
    """★★★ **후계 매핑 금지** — `KOREX`를 `CJGLS`로 바꾸지 않는다(문서에 없다)."""
    ok, why = RULES.validate("KOREX", "1234567890")
    assert ok is False
    assert RULES.UNSUPPORTED_LABEL in why
    assert "CJGLS" not in why


def test_an_unknown_code_is_refused():
    ok, why = RULES.validate("NOSUCHCODE", "123")
    assert ok is False and "코드표에 없는" in why


def test_the_send_gate_uses_the_table_end_to_end():
    """★★ 관문이 **표를 본다** — 모양만 보던 F45에서 강화됐다."""
    from src.seller_console.orders.sync_service import courier_code_hold
    assert courier_code_hold("coupang", "CJGLS", "1234567890") == ""
    assert "쿠팡 규격" in courier_code_hold("coupang", "CJGLS", "123")
    assert courier_code_hold("coupang", "KOREX", "1234567890")
    assert courier_code_hold("coupang", "NOSUCHCODE", "1234567890")
    # 다른 마켓은 그대로 — 코드표를 모르는 채로 막는 것도 발명이다.
    assert courier_code_hold("smartstore", "한진택배", "123") == ""


# ---------------------------------------------------------------------------
# 카탈로그에 쿠팡 열이 붙었다 (기존 축은 그대로)
# ---------------------------------------------------------------------------

def test_the_catalog_gained_a_coupang_column_without_losing_the_others():
    from src.seller_console.orders.courier_catalog import get_courier_catalog
    rows = get_courier_catalog(include_dynamic=False)
    for r in rows:
        assert "trackingmore_code" in r and "sweet_code" in r     # 기존 축 보존
        assert "coupang_code" in r and "coupang_status" in r


def test_the_ten_builtin_couriers_all_map_to_coupang_codes():
    """★ 우리가 실제로 쓰는 10곳은 전부 쿠팡 코드가 붙어야 쓸모가 있다."""
    from src.seller_console.orders.courier_catalog import get_courier_catalog
    rows = get_courier_catalog(include_dynamic=False)
    unmapped = [r["name"] for r in rows if not r["coupang_code"]]
    assert not unmapped, unmapped


def test_the_other_market_columns_are_empty_not_guessed():
    """★★ 네이버·11번가 코드표가 **아직 없다** — 빈칸이 정직한 값이다."""
    from src.seller_console.orders.courier_catalog import get_courier_catalog
    for r in get_courier_catalog(include_dynamic=False):
        assert r["naver_code"] == "" and r["elevenst_code"] == ""


# ---------------------------------------------------------------------------
# 표는 표대로 둔다
# ---------------------------------------------------------------------------

def test_the_data_file_holds_no_logic():
    """★ 문서를 옮긴 표에 로직이 섞이면 다음 개정 때 **무엇이 문서인지** 갈린다."""
    import inspect

    from src.seller_console.orders import coupang_courier_codes as DATA
    src = inspect.getsource(DATA)
    body = src.split("COUPANG_COURIERS", 1)[1]
    assert "def " not in body, "표 파일에 함수가 생겼다 — 규칙은 rules 쪽에 둔다"


def test_the_document_version_is_recorded():
    """★ 다음 개정과 대조할 수 있게 **문서 버전**을 남긴다."""
    import inspect

    from src.seller_console.orders import coupang_courier_codes as DATA
    assert "2609170000" in inspect.getsource(DATA)

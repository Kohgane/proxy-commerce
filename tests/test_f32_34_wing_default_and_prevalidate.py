"""F32-3·4 계약 — 「어느 이름으로 읽나」와 「누구 것인가」는 다른 질문이다.

## F32-3 실측 (오너 2026-09-18)

Wing 로그인 ID 기본값(`shanks8` / `chrisvaud`)이 **마켓 연동 화면에 안 채워졌다.**

원인: 제안이 `resolve_upload_account()`에 물었는데, 그건
**「업로더가 어느 이름으로 읽나」**다 — 무접두 자격이 있으면 `""`를 낸다(무접두로 읽으니까).
오너 Render엔 접두(`COUPANG_GOGANE_*`)와 무접두가 **둘 다** 있어서 답이 `""`였고,
`WING_USER_IDS.get("")` → 빈 값 → **제안이 통째로 사라졌다.**

물어야 할 것은 **「이 자격이 누구 것인가」**다. 무접두여도 **업체코드로 사업체를 안다**
(`A01381223` → 고가네). → `business_account()`.

> ★ 같은 모듈 안에서도 **질문이 다르면 함수가 다르다.** 비슷해 보인다고 하나로 쓰면
> 한쪽 답이 다른 쪽에서 틀린다.

다중 셀러 보호는 그대로다 — 모르는 업체코드면 `None`이고, 제안은 빈 값이다.

## F32-4

**저장 → 사전검증 「통과」.** 연동 화면에 넣은 값이 주입돼 쿠팡이 통과해야 등록으로 간다.

라이브 호출 0 · 마켓 호출 0.
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]

# 쿠팡 등록에 필요한 배송 7필드 + API 자격 3 — 연동 화면이 받는 그 이름들.
FULL_COUPANG = {
    "COUPANG_ACCESS_KEY": "ak", "COUPANG_SECRET_KEY": "sk", "COUPANG_VENDOR_ID": "A01381223",
    "COUPANG_VENDOR_USER_ID": "shanks8",
    "COUPANG_RETURN_CENTER_CODE": "1000274592",
    "COUPANG_OUTBOUND_SHIPPING_PLACE_CODE": "7437895",
    "COUPANG_RETURN_ZIP_CODE": "06236",
    "COUPANG_RETURN_ADDRESS": "서울특별시 강남구 테헤란로 123",
    "COUPANG_RETURN_CHARGE_NAME": "고가네CS",
    "COUPANG_COMPANY_CONTACT_NUMBER": "02-123-4567",
}


@pytest.fixture
def clean_env(monkeypatch):
    for k in list(os.environ):
        if k.startswith("COUPANG_"):
            monkeypatch.delenv(k, raising=False)
    return monkeypatch


# ---------------------------------------------------------------------------
# F32-3 — 사업체는 업체코드로 안다
# ---------------------------------------------------------------------------

def test_business_is_known_even_when_the_account_name_is_empty(clean_env):
    """★ **F32-3의 판정 지점** — 접두와 무접두가 **둘 다** 있어도 사업체를 안다.

    오너 Render의 실제 상태다. 예전엔 여기서 제안이 사라졌다.
    """
    from src.seller_console import market_cred_view as V
    for k, v in (("GOGANE_ACCESS_KEY", "a"), ("GOGANE_SECRET_KEY", "s"),
                 ("GOGANE_VENDOR_ID", "A01381223"),
                 ("ACCESS_KEY", "a"), ("SECRET_KEY", "s"), ("VENDOR_ID", "A01381223")):
        clean_env.setenv(f"COUPANG_{k}", v)
    assert V.resolve_upload_account() == "", "이 함수는 「어느 이름으로 읽나」다 — 무접두다"
    assert V.business_account() == "gogane", "「누구 것인가」는 업체코드가 답한다"


def test_the_two_questions_stay_separate(clean_env):
    """접두만 있으면 둘 다 계정 이름을 낸다 — 갈리는 건 무접두가 끼었을 때뿐이다."""
    from src.seller_console import market_cred_view as V
    for k, v in (("WOOJOO_ACCESS_KEY", "a"), ("WOOJOO_SECRET_KEY", "s"),
                 ("WOOJOO_VENDOR_ID", "A01504840")):
        clean_env.setenv(f"COUPANG_{k}", v)
    assert V.resolve_upload_account() == "woojoo"
    assert V.business_account() == "woojoo"


@pytest.mark.parametrize("vendor,expect", [("A01381223", "shanks8"),
                                           ("A01504840", "chrisvaud")])
def test_wing_id_is_suggested_for_each_business(clean_env, vendor, expect):
    """★ 사업체별 실값 — 업체코드가 곧 사업체다."""
    from src.seller_console import market_credentials as mc
    for k, v in (("ACCESS_KEY", "a"), ("SECRET_KEY", "s"), ("VENDOR_ID", vendor)):
        clean_env.setenv(f"COUPANG_{k}", v)
    assert mc._suggest_value("COUPANG_VENDOR_USER_ID") == expect


def test_an_unknown_vendor_gets_no_suggestion(clean_env):
    """★ 다중 셀러 보호 — 모르는 업체코드면 **아무것도 제안하지 않는다**."""
    from src.seller_console import market_credentials as mc
    from src.seller_console import market_cred_view as V
    for k, v in (("ACCESS_KEY", "a"), ("SECRET_KEY", "s"), ("VENDOR_ID", "A09999999")):
        clean_env.setenv(f"COUPANG_{k}", v)
    assert V.business_account() == ""
    assert mc._suggest_value("COUPANG_VENDOR_USER_ID") == ""


def test_the_suggestion_reaches_the_screen_model(clean_env):
    """화면 모델(`status`)까지 실제로 실린다 — 함수만 맞고 화면이 비면 소용없다."""
    from src.seller_console import market_credentials as mc
    for k, v in (("ACCESS_KEY", "a"), ("SECRET_KEY", "s"), ("VENDOR_ID", "A01381223")):
        clean_env.setenv(f"COUPANG_{k}", v)
    st = mc.status("u-none", "coupang")
    wing = [f for f in st["fields"] if f["env"] == "COUPANG_VENDOR_USER_ID"][0]
    assert wing["suggest"] == "shanks8", wing


def test_a_saved_value_is_never_overwritten_by_the_suggestion(clean_env):
    """사람이 넣은 값이 이긴다 — 상수가 덮으면 그건 도움이 아니다."""
    from src.seller_console import market_credentials as mc
    for k, v in (("ACCESS_KEY", "a"), ("SECRET_KEY", "s"), ("VENDOR_ID", "A01381223"),
                 ("VENDOR_USER_ID", "somebody-else")):
        clean_env.setenv(f"COUPANG_{k}", v)
    st = mc.status("u-none", "coupang")
    wing = [f for f in st["fields"] if f["env"] == "COUPANG_VENDOR_USER_ID"][0]
    assert wing["has_value"] is True
    assert wing["suggest"] == "", "이미 값이 있는 칸에 제안을 붙였다"


def test_secrets_never_get_a_suggestion(clean_env):
    from src.seller_console import market_credentials as mc
    for f in mc.status("u-none", "coupang")["fields"]:
        if f["secret"]:
            assert not f.get("suggest"), f["env"]


# ---------------------------------------------------------------------------
# F32-4 — 저장 → 사전검증 「통과」
# ---------------------------------------------------------------------------

def test_saved_credentials_make_the_coupang_precheck_pass(clean_env, tmp_path):
    """★★ **F32-4의 판정 지점** — 연동 화면에 넣은 값이 주입돼 쿠팡이 **통과**한다.

    env엔 쿠팡 값이 하나도 없는 상태에서 시작한다(오너 실측 ④: 두 저장소 모두 비어 있음).
    """
    from src.seller_console import market_credentials as mc
    from src.seller_console.upload_dispatcher import UploadDispatcher
    # `_DATA_DIR`은 **모듈 로드 시점 상수**다 — env를 바꿔도 안 바뀐다(그렇게 썼다가
    #   테스트가 레포의 `data/market_credentials/`에 실제로 파일을 썼다). 상수를 세운다.
    clean_env.setattr(mc, "_DATA_DIR", str(tmp_path), raising=False)

    with patch.object(mc, "_pg_links", return_value=None):   # 파일 저장소로 고정
        mc.save("seller-1", "coupang", dict(FULL_COUPANG))
        # 저장 전에는 막힌다 — 게이트가 살아 있다는 뜻이다.
        blocked = UploadDispatcher().prevalidate({"title": "수행방패", "price": 9900},
                                                 ["coupang"])[0]
        assert blocked.ok is False and blocked.error_code == "token_missing"

        # 등록 경로가 실제로 쓰는 그 주입으로 다시 잰다.
        with mc.seller_market_env("seller-1", ["coupang"]):
            passed = UploadDispatcher().prevalidate({"title": "수행방패", "price": 9900},
                                                    ["coupang"])[0]
    assert passed.ok is True, passed.hint


def test_one_missing_shipping_field_still_blocks(clean_env, tmp_path):
    """일곱 중 하나만 비어도 막는다 — 반쯤 채운 채 등록 보내면 쿠팡이 거부한다."""
    from src.seller_console import market_credentials as mc
    from src.seller_console.upload_dispatcher import UploadDispatcher
    clean_env.setattr(mc, "_DATA_DIR", str(tmp_path), raising=False)
    partial = dict(FULL_COUPANG)
    partial.pop("COUPANG_RETURN_ZIP_CODE")

    with patch.object(mc, "_pg_links", return_value=None):
        mc.save("seller-2", "coupang", partial)
        with mc.seller_market_env("seller-2", ["coupang"]):
            res = UploadDispatcher().prevalidate({"title": "수행방패", "price": 9900},
                                                 ["coupang"])[0]
    assert res.ok is False
    assert "COUPANG_RETURN_ZIP_CODE(반품지우편번호)" in res.hint
    assert "확인한 곳:" in res.hint, "어느 저장소를 봤는지 말하지 않는다"


def test_the_screen_accepts_every_field_the_precheck_requires():
    """화면에 **입력 칸이 없는 값**을 사전검증이 요구하면, 셀러는 영원히 못 채운다."""
    from src.seller_console.market_cred_view import COUPANG_SHIP_FIELDS
    from src.seller_console.market_credentials import MARKET_CRED_FIELDS
    on_screen = {f["env"] for f in MARKET_CRED_FIELDS["coupang"]}
    for env, label in COUPANG_SHIP_FIELDS:
        assert env in on_screen, f"{env}({label}) 칸이 화면에 없다"

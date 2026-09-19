"""src/seller_console/market_cred_view.py — 마켓 자격을 **한 자리에서** 판정한다 (F29).

## 왜 이 파일이 생겼나

오너 실측(2026-09-16): 대시보드는 쿠팡을 「자격 설정됨」이라 하고, 같은 계정으로 등록
사전검증을 돌리면 「미입력 — 7필드」였다. **한 화면이 다른 화면을 반박한다.**

갈라 보니 같은 자격을 읽는 자리가 셋이었고, 셋이 서로 다른 규약을 썼다:

| 읽는 쪽 | 이름 규약 | 보는 것 |
|---|---|---|
| 대시보드 타일 | 계정 접두 `COUPANG_GOGANE_*` | access·secret |
| 등록 사전검증 | **무접두만** | access·secret + 배송 7필드 |
| 실제 업로더 | 접두 우선 + 무접두 폴백 | 배송 7필드 |

오너는 접두 이름으로 넣어 뒀다. 그래서 대시보드와 업로더는 값을 찾고,
**사전검증만 못 찾아** 「미입력」이라고 했다.

> ★ **같은 값을 두 자리가 다른 규약으로 읽으면, 한쪽은 반드시 거짓말을 한다.**
> 판정기를 새로 쓰지 않는다 — **업로더의 읽기를 그대로 부른다.**

## 규약

- 값은 **절대 돌려주지 않는다.** 있는지 없는지와 **어디서 왔는지**만.
- 못 물어봤으면 그렇게 말한다(빈 값과 구분).
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

# 쿠팡 등록에 반드시 필요한 배송 필드 — 라벨은 셀러가 Wing에서 보는 이름 그대로.
COUPANG_SHIP_FIELDS = (
    ("COUPANG_VENDOR_USER_ID", "Wing 로그인 ID"),
    ("COUPANG_RETURN_CENTER_CODE", "반품지센터코드"),
    ("COUPANG_OUTBOUND_SHIPPING_PLACE_CODE", "출고지코드"),
    ("COUPANG_RETURN_ZIP_CODE", "반품지우편번호"),
    ("COUPANG_RETURN_ADDRESS", "반품지주소"),
    ("COUPANG_RETURN_CHARGE_NAME", "반품지담당자명"),
    ("COUPANG_COMPANY_CONTACT_NUMBER", "반품지연락처"),
)

# 사업체별 Wing 로그인 ID — 오너 실측(2026-09-16). **자격이 아니라 로그인 아이디**다
#   (비밀이 아니고, 쿠팡 API가 등록 요청에 요구하는 값이다). 화면에서 편집 가능하다.
#   사업체×마켓×ID 정본 표는 볼트 결정문에 있다.
WING_USER_IDS = {
    "gogane": "shanks8",
    "woojoo": "chrisvaud",
}


def _read_state() -> dict:
    """저장소를 **읽을 수 있었나** — `market_credentials.read_state`가 정본."""
    try:
        from src.seller_console.market_credentials import read_state
        return read_state()
    except Exception as exc:
        logger.warning("[마켓 자격] 읽기 상태 조회 실패: %s", exc)
        return {"ok": True, "reason": ""}      # 모르면 **판단하지 않는다**(기존 문장 유지)


def _uploader_reader(account: str = ""):
    """업로더의 배송 env 읽기를 그대로 쓴다 — 접두 우선 + 무접두 폴백(재구현 0)."""
    from src.uploaders.coupang_uploader import CoupangUploader
    up = CoupangUploader.__new__(CoupangUploader)      # __init__은 네트워크·로깅을 탄다
    up.account = str(account or "")
    return up


def coupang_shipping_state(account: str = "") -> dict:
    """`{missing: [(env, label)], present: [...], source: str, account: str}`.

    `source`는 **어디서 읽었는지**다 — 「미입력」이라고 말할 때 어느 저장소를 봤는지
    같이 말하지 않으면, 셀러는 이미 넣어 둔 값을 또 넣는다(오너가 실제로 그랬다).
    """
    acct = str(account or "").strip()
    if not acct:
        acct = resolve_upload_account()
    missing, present, prefixed = [], [], 0
    try:
        up = _uploader_reader(acct)
        for env, label in COUPANG_SHIP_FIELDS:
            val = ""
            try:
                val = (up._ship_env(env) or "").strip()
            except Exception:
                val = (os.getenv(env) or "").strip()
            if val:
                present.append((env, label))
                if env not in os.environ:      # 무접두엔 없다 = 접두에서 왔다
                    prefixed += 1
            else:
                missing.append((env, label))
    except Exception as exc:
        logger.warning("[마켓 자격] 쿠팡 배송 상태 조회 실패: %s", exc)
        # **못 물어본 것을 「없다」고 하지 않는다** — 그러면 멀쩡한 자격을 미입력이라 부른다.
        return {"missing": [], "present": [], "unknown": True, "account": acct,
                "source": "확인하지 못했습니다"}

    read_failed = ""
    if not present:
        # F34-1: **「비어 있음」이라 말하기 전에 「읽을 수 있었나」를 먼저 묻는다.**
        #   실측(2026-09-19): 6칸을 넣고 저장했는데 검증기는 7칸 전부 「비어 있음」이라 했다.
        #   복호화가 실패하거나 저장소가 갈리면 빈 dict가 올라왔고, 그게 「입력한 적 없음」으로
        #   보였다. 못 읽은 것을 「없다」고 말하면 사람은 이미 넣은 값을 또 넣는다.
        read = _read_state()
        if not read.get("ok"):
            read_failed = str(read.get("reason") or "사유 미상")
            src = f"저장된 값을 읽지 못했습니다 — {read_failed}"
        else:
            src = ("마켓 연동 화면에 입력된 값 · 서버 환경변수 둘 다 비어 있음" if not acct
                   else f"쿠팡 계정 「{acct}」 서버 환경변수 · 마켓 연동 화면 둘 다 비어 있음")
    elif prefixed and acct:
        src = f"서버 환경변수(계정 접두 COUPANG_{acct.upper()}_*)"
    else:
        src = "마켓 연동 화면에 입력된 값(또는 무접두 환경변수)"
    return {"missing": missing, "present": present, "unknown": False,
            "account": acct, "source": src, "read_failed": read_failed}


_BASE_KEYS = ("COUPANG_ACCESS_KEY", "COUPANG_SECRET_KEY", "COUPANG_VENDOR_ID")


def resolve_upload_account() -> str:
    """이 요청에서 **업로더가 실제로 쓸 계정**. 빈 문자열 = 무접두(계정 없음).

    ## 왜 이 함수가 판정의 뿌리인가

    실측(F29): 셀러 콘솔 등록 경로는 `CoupangUploader()`를 **계정 없이** 만든다
    (`src/channel_sync/coupang_uploader.py:27`). 계정이 없으면 `_ship_env`는 무접두
    이름만 읽는다. 그래서 오너가 Render에 `COUPANG_GOGANE_*`로 넣어 둔 자격이
    **이 경로에선 아예 안 보였다** — 「미입력 7필드」는 이 경로에 한해 사실이었다.
    (대시보드는 접두를 읽으니 「자격 설정됨」. 둘 다 거짓말은 아니었고, **서로 다른 것을
    보고 있었다.**)

    ## 순서가 중요하다 — 무접두가 먼저다

    무접두 자격은 **셀러가 마켓 연동 화면에 넣은 자기 키**가 `seller_market_env`로
    주입된 것이다(멀티 셀러). 그게 있으면 그대로 쓴다 — 지금까지의 그 경로다.
    무접두가 없을 때만 계정 접두로 내려간다. 순서를 뒤집으면 **다른 셀러의 등록이
    오너 계정 자격으로 나간다.**
    """
    if all((os.getenv(k) or "").strip() for k in _BASE_KEYS):
        return ""
    try:
        from src.pipeline.coupang_replicate import COUPANG_ACCOUNTS, _account_creds
        for acct in COUPANG_ACCOUNTS:
            access, secret, vendor = _account_creds(acct)
            if access and secret and vendor:
                return acct
    except Exception as exc:
        logger.warning("[마켓 자격] 쿠팡 계정 해석 실패: %s", exc)
    return ""


def coupang_api_state(account: str = "") -> dict:
    """API 자격(access·secret·vendor) — **업로더가 읽을 그 자리**를 본다."""
    acct = str(account or "").strip() or resolve_upload_account()
    try:
        if acct:
            from src.pipeline.coupang_replicate import _account_creds
            access, secret, vendor = _account_creds(acct)
        else:
            access, secret, vendor = (os.getenv(k, "").strip() for k in _BASE_KEYS)
    except Exception as exc:
        logger.warning("[마켓 자격] 쿠팡 API 자격 조회 실패: %s", exc)
        return {"missing": [], "unknown": True, "account": acct,
                "source": "확인하지 못했습니다"}
    missing = []
    if not access:
        missing.append(("COUPANG_ACCESS_KEY", "액세스 키"))
    if not secret:
        missing.append(("COUPANG_SECRET_KEY", "시크릿 키"))
    if not vendor:
        missing.append(("COUPANG_VENDOR_ID", "업체코드"))
    return {"missing": missing, "unknown": False, "account": acct,
            "source": (f"쿠팡 계정 「{acct}」 서버 환경변수"
                       if acct else "마켓 연동 화면에 입력된 값")}


def _default_account() -> str:
    """기본 계정 — 업로더가 실제로 쓸 계정과 **같은 답**을 쓴다(판정기 2개 금지)."""
    return resolve_upload_account()


def business_account() -> str:
    """이 서버의 쿠팡 자격이 **어느 사업체 것인가**. 모르면 빈 문자열 (F32-3).

    `resolve_upload_account()`와 **다른 질문**이다:
      · `resolve_upload_account()` = 「업로더가 **어느 이름으로 읽을** 것인가」
        → 무접두가 있으면 `""`(무접두로 읽는다)
      · 여기 = 「그 자격이 **누구 것인가**」
        → 무접두여도 **업체코드로 사업체를 안다**

    실측(F32-3): 오너 Render엔 접두(`COUPANG_GOGANE_*`)와 무접두가 **둘 다** 있다.
    그래서 `resolve_upload_account()`가 `""`를 내고, Wing 아이디 제안이
    `WING_USER_IDS.get("")` → 빈 값이 됐다 — **화면에 안 채워졌다.**

    다른 셀러 보호는 그대로다: 무접두 업체코드가 우리가 아는 둘 중 어느 것도 아니면
    `resolve_base_account()`가 `None`을 내고, 여기도 빈 문자열이다.
    **남의 Wing 아이디를 남의 칸에 채우지 않는다.**
    """
    acct = resolve_upload_account()
    if acct:
        return acct
    try:
        from src.pipeline.coupang_replicate import resolve_base_account
        return resolve_base_account() or ""
    except Exception as exc:
        logger.warning("[마켓 자격] 사업체 해석 실패: %s", exc)
        return ""


def coupang_wing_user_id(account: str = "") -> str:
    """이 계정의 Wing 로그인 ID — 이미 넣어 둔 값이 있으면 **그것이 우선**이다.

    기본값은 오너 실측치다. 화면이 이 값을 미리 채우되 편집을 막지 않는다 —
    사람이 고친 값을 코드 상수가 덮으면 그건 도움이 아니다.
    """
    acct = str(account or "").strip() or _default_account()
    try:
        saved = (_uploader_reader(acct)._ship_env("COUPANG_VENDOR_USER_ID") or "").strip()
    except Exception:
        saved = (os.getenv("COUPANG_VENDOR_USER_ID") or "").strip()
    return saved or WING_USER_IDS.get(acct, "")

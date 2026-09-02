"""src/pipeline/agency_link.py — K2: **연동대행사** 모델(톡스토어 등).

지금까지의 마켓은 **판매자가 자기 앱 키를 직접 넣는** 모델이었다(쿠팡 Access/Secret, 네이버
Client ID/Secret). 대행사 모델은 축이 하나 더 있다:

    대행사 앱 Admin키(서버 비밀 1개)  ×  판매자별 API 인증키(판매자마다 1개)

Admin키는 **우리 서버 것**이라 판매자에게 보이면 안 되고, 판매자 인증키는 **판매자 것**이라
우리가 평문으로 갖고 있으면 안 된다. 이 모듈은 그 둘을 갈라 놓고 **매핑 상태**만 판정한다.

**여기서 하지 않는 것(발명 0):**
  · 실전송 — 톡스토어 통과 이력 정본이 없다. 키·계약 전엔 아무것도 보내지 않는다.
  · 페이로드 빌더 — 필수 필드 표가 문서 실측(K0)으로 확정되기 전엔 짓지 않는다.
    현재 컨테이너에서 카카오 문서 도메인이 차단돼(HTTP 000) 실측을 못 했다.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# 대행사 축을 쓰는 마켓. 판매자가 앱을 직접 만들지 않고 **우리 앱에 자기 스토어를 매핑**한다.
AGENCY_MARKETS = ("talkstore",)

# 대행사 앱 Admin키 — **서버 비밀 1개**. 판매자별로 갈리지 않는다.
ADMIN_KEY_ENV = "TALKSTORE_ADMIN_KEY"
# 판매자가 붙여넣는 자기 인증키(암호화 저장). 값은 `market_credentials`가 Fernet으로 갖는다.
SELLER_KEY_FIELD = "TALKSTORE_SELLER_API_KEY"
SELLER_STORE_FIELD = "TALKSTORE_STORE_ID"

# 매핑 상태 — 화면·어댑터가 같은 말을 쓰게 한 곳에 둔다.
STATUS = {
    "unmapped": {"ko": "미매핑", "desc": "판매자 인증키가 아직 없습니다"},
    "pending": {"ko": "매핑 대기", "desc": "인증키는 있으나 대행사 앱 승인·매핑이 끝나지 않았습니다"},
    "active": {"ko": "활성", "desc": "매핑 완료 — 등록 가능"},
}

# 카카오 대행사 정책상 판매자 1곳이 동시에 매핑할 수 있는 대행사 수 상한.
#   ※ 문서 실측(K0) 전이라 **강제하지 않고** 화면 안내에만 쓴다. 확정되면 게이트로 올린다.
MAX_AGENCIES_PER_SELLER_HINT = 2


def admin_key_configured() -> bool:
    """대행사 Admin키가 서버에 있는가. **값은 절대 반환하지 않는다**(존재 여부만)."""
    return bool(str(os.getenv(ADMIN_KEY_ENV, "")).strip())


def _seller_creds(seller_id: str, market: str = "talkstore") -> dict:
    """판매자 자격을 복호화해 읽는다. 값은 이 함수 밖으로 **원문 그대로 나가지 않는다**."""
    try:
        from src.seller_console import market_credentials as mc
        return mc.get(seller_id, market) or {}
    except Exception as exc:
        logger.warning("대행사 판매자 자격 조회 실패(%s): %s", market, exc)
        return {}


def mapping_status(seller_id: str, market: str = "talkstore") -> dict:
    """판매자의 매핑 상태. {status, status_ko, desc, has_seller_key, admin_ready, blockers}.

    **키 값은 담지 않는다** — 있고 없고와 다음에 뭘 해야 하는지만 말한다.
    """
    creds = _seller_creds(seller_id, market)
    has_key = bool(str(creds.get(SELLER_KEY_FIELD, "") or "").strip())
    admin_ready = admin_key_configured()

    blockers = []
    if not admin_ready:
        blockers.append("대행사 앱 Admin키 미설정(서버) — 대행사 등록 심사 통과 후 설정")
    if not has_key:
        blockers.append("판매자 API 인증키 미입력")

    if not has_key:
        status = "unmapped"
    elif not admin_ready:
        status = "pending"
    else:
        status = "pending"      # 키가 둘 다 있어도 **매핑 승인 전엔 활성이 아니다**(가짜 활성 금지)
    meta = STATUS[status]
    return {"market": market, "status": status, "status_ko": meta["ko"], "desc": meta["desc"],
            "has_seller_key": has_key, "admin_ready": admin_ready, "blockers": blockers}


def ready_to_register(seller_id: str, market: str = "talkstore") -> tuple:
    """등록 가능한가. 반환 (ok, 사유).

    **지금은 언제나 False다.** 통과 이력 정본이 없어 페이로드를 지을 수 없고,
    정본 없이 보내면 카나리 6차 왕복을 반복한다. 키가 다 들어와도 문서 실측(K0)이
    먼저다 — 그때 이 함수의 판정 근거가 바뀐다.
    """
    st = mapping_status(seller_id, market)
    if st["blockers"]:
        return False, " · ".join(st["blockers"])
    return False, ("톡스토어 페이로드 정본 미확보 — 공개 문서 실측 전까지 전송하지 않습니다"
                   "(추측 전송 금지).")

"""Y7-L(오너 2026-10-10 19:55 KST) — 네이버 A/S 전화번호를 **셀러 설정**으로(스토어별). 서버 환경변수는 폴백.

증거: 폰 카드 「A/S 연락처 넣기 →」가 마켓 연동 화면(/seller/markets/connect)으로 갔는데 그 화면엔 Client ID·Secret·
Channel ID 칸뿐 — A/S 전화를 넣을 곳이 없었다(값은 서버 환경변수 `NAVER_<STORE>_AS_PHONE` → `NAVER_AS_PHONE`만).

- 저장: `naver_as:<범위>`(app_state) = `{스토어 코드: 전화}`. 범위는 고시 기본값과 같다 — 공유 마켓 사용자(관리자·가족)는 한 벌,
  그 밖의 셀러는 자기 것. 스토어 코드가 없는 셀러(자기 키 한 벌)는 `default`.
- 읽기 순서: 설정(그 스토어) → 서버 환경변수(`_acct_env('NAVER_AS_PHONE')` — 계정 접두 → 무접두). 화면엔 env 이름을 쓰지 않는다.
"""
from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_KEY = "naver_as:"
DEFAULT = "default"
#: 공유 마켓 스토어(U0b) — 화면 순서·이름
STORES = (("chezgoga", "셰고가"), ("gocosmos", "고코스모스"))
_PHONE = re.compile(r"^[0-9][0-9\-\s]{6,18}[0-9]$")


def _scope(seller_id: str = "", shared: Optional[bool] = None) -> str:
    from src.uploaders.naver_notice import _scope as notice_scope
    return notice_scope(seller_id, shared)


def get_all(seller_id: str = "", shared: Optional[bool] = None) -> Dict[str, str]:
    try:
        from src.db import image_translate_queue_pg as st
        v = st.state_get(_KEY + _scope(seller_id, shared)) or {}
        return {str(k): str(p).strip() for k, p in v.items() if str(p or "").strip()}
    except Exception as exc:                                       # noqa: BLE001 — 못 읽으면 env 폴백
        logger.debug("[네이버 A/S] 설정 읽기 실패(env 폴백): %s", exc)
        return {}


def saved(account: str = "", seller_id: str = "", shared: Optional[bool] = None) -> str:
    """설정에 저장된 그 스토어 A/S 전화 — 없으면 ''."""
    return get_all(seller_id, shared).get(str(account or "") or DEFAULT, "")


def normalize(phone: str) -> str:
    p = re.sub(r"\s+", "", str(phone or ""))
    if p and not _PHONE.match(p):
        raise ValueError("A/S 전화번호는 숫자와 -만 넣어 주세요(예: 010-1234-5678)")
    return p


def save(values: Dict[str, str], seller_id: str = "", shared: Optional[bool] = None) -> Dict[str, str]:
    """`{스토어: 전화}` 저장 — 빈 값은 그 스토어 설정을 지운다(서버 기본값으로 돌아감)."""
    cur = get_all(seller_id, shared)
    for k, v in (values or {}).items():
        k = str(k or "") or DEFAULT
        p = normalize(v)
        if p:
            cur[k] = p
        else:
            cur.pop(k, None)
    from src.db import image_translate_queue_pg as st
    st.state_set(_KEY + _scope(seller_id, shared), cur)
    return cur


def rows(shared: bool, env_lookup) -> List[Dict[str, str]]:
    """연동 화면 줄 — `[{account, label, value, source}]`. source: 설정 / 서버 기본값 / 없음(env 이름은 쓰지 않는다).
    `env_lookup(account)` = 그 스토어의 서버 환경변수 값(업로더 `_acct_env`)."""
    stores = list(STORES) if shared else [(DEFAULT, "내 스토어")]
    cur = get_all(shared=shared)
    out = []
    for acct, label in stores:
        mine = cur.get(acct, "")
        env = "" if mine else (env_lookup(acct if acct != DEFAULT else "") or "")
        out.append({"account": acct, "label": label, "value": mine or env,
                    "source": "설정" if mine else ("서버 기본값" if env else "없음")})
    return out

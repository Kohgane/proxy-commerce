"""src/seller_console/user_messages.py — 셀러 화면에 나가는 **설정 누락 문장**을 한 곳에서.

## 왜 (M1-1, 중국 유저 실캡처 2026-09-26)

모바일 화면에 「다음 환경변수를 Wing 배송정보 값으로 설정하세요: COUPANG_…」이 떴다. 셀러는 환경변수를
모르고, 고칠 수도 없다(그건 우리 서버 설정의 이름이다). 게다가 등록 경로가 문장을 **이어 붙여**
「전송 전에 보류했습니다 — 쿠팡 업로드 실패: 쿠팡 출고지/반품지 … 환경변수 …」처럼 새 문구 뒤에 옛 문구가 따라 나왔다.

규칙:
- 화면 문장은 **칸 이름**(연동 화면의 라벨)으로 말한다. env 이름은 로그에만 남는다.
- 무엇을 하면 되는지(「마켓 연동 › 쿠팡에서 불러오기」)와 **그 화면 주소**를 함께 준다.
- 문장을 만드는 자리는 여기 하나다 — 업로더·브리지·사전검증이 전부 이걸 부른다.
"""
from __future__ import annotations

import re
from typing import Dict, Iterable, List

CONNECT_URL = "/seller/markets/connect/{market}"
_ACCOUNT_PREFIX = re.compile(r"^COUPANG_(GOGANE|WOOJOO)_")


def connect_url(market: str) -> str:
    return CONNECT_URL.format(market=str(market or "").strip() or "coupang")


def _labels() -> Dict[str, str]:
    """env → 연동 화면의 칸 이름. 화면이 쓰는 라벨 그대로(두 벌 금지)."""
    out: Dict[str, str] = {}
    try:
        from src.seller_console.market_credentials import MARKET_CRED_FIELDS
        for fields in MARKET_CRED_FIELDS.values():
            for f in fields:
                out[f["env"]] = str(f.get("label") or f["env"])
    except Exception:                                       # pragma: no cover
        pass
    try:
        from src.seller_console.market_cred_view import COUPANG_SHIP_FIELDS
        for env, label in COUPANG_SHIP_FIELDS:
            out.setdefault(env, label)
    except Exception:                                       # pragma: no cover
        pass
    return out


def label_for(env: str) -> str:
    """env 이름 → 칸 이름. 계정 접두(`COUPANG_GOGANE_…`)는 떼고 찾는다. 모르면 「설정 값」."""
    raw = str(env or "").split("(")[0].split("/")[0].strip()
    base = _ACCOUNT_PREFIX.sub("COUPANG_", raw)
    return _labels().get(base) or "설정 값"


def _uniq(items: Iterable[str]) -> List[str]:
    out: List[str] = []
    for x in items:
        if x and x not in out:
            out.append(x)
    return out


def coupang_shipping_missing(envs: Iterable[str]) -> str:
    """쿠팡 출고지·반품지(배송정보)가 비었다."""
    labels = _uniq(label_for(e) for e in envs)
    tail = f"(빈 칸: {' · '.join(labels)})" if labels else ""
    return f"쿠팡 출고지·반품지가 비어 있어요{tail} → 마켓 연동 › 쿠팡에서 불러오기"


def credentials_missing(market_label: str, envs: Iterable[str]) -> str:
    """마켓 연결 키가 비었다."""
    labels = _uniq(label_for(e) for e in envs)
    tail = f"(빈 칸: {' · '.join(labels)})" if labels else ""
    return f"{market_label} 연결 정보가 비어 있어요{tail} → 마켓 연동 › {market_label}에서 입력"


def coupang_courier_missing() -> str:
    """쿠팡 택배사 코드가 정해지지 않았다(쿠팡 목록에 있는 코드만 보낸다)."""
    return "쿠팡 택배사가 정해지지 않았어요 → 마켓 연동 › 쿠팡에서 택배사를 확인해 주세요"

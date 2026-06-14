"""셀프서비스 마켓 연결 — 셀러별 마켓 자격증명 저장 / 연결 / 주입.

SaaS 다중 셀러 대비: 각 셀러가 자신의 마켓 API 키를 직접 입력·저장·연결 테스트한다.
환경변수(단일 테넌트/오너) 방식과 공존한다.

- 저장: `data/market_credentials/<seller_id>.json` (Fernet 암호화, 키 없으면 평문+경고)
- 주입: `seller_market_env(seller_id, market)` 컨텍스트로 표준 환경변수에 일시 주입
- 폴백: 셀러 저장값이 없으면 전역 환경변수(os.environ)를 그대로 사용

암호화 키: `MARKET_CRED_ENC_KEY`(Fernet 키) 우선, 없으면 `SECRET_KEY` 파생.
둘 다 없으면 평문 저장(개발용) — 운영에서는 반드시 키를 설정할 것.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DATA_DIR = os.getenv("MARKET_CRED_DIR") or os.path.join("data", "market_credentials")


# 마켓별 입력 필드 정의 (env = 코드가 실제로 읽는 표준 환경변수 이름).
# secret=True 인 값은 화면에 마스킹해서 표시한다.
MARKET_CRED_FIELDS: Dict[str, List[Dict[str, Any]]] = {
    "coupang": [
        {"env": "COUPANG_ACCESS_KEY", "label": "Access Key", "secret": True, "required": True},
        {"env": "COUPANG_SECRET_KEY", "label": "Secret Key", "secret": True, "required": True},
        {"env": "COUPANG_VENDOR_ID", "label": "Vendor ID", "secret": False, "required": True},
    ],
    "smartstore": [
        {"env": "NAVER_CLIENT_ID", "label": "Client ID", "secret": False, "required": True},
        {"env": "NAVER_CLIENT_SECRET", "label": "Client Secret", "secret": True, "required": True},
        {"env": "NAVER_CHANNEL_ID", "label": "Channel ID (선택)", "secret": False, "required": False},
    ],
    "elevenst": [
        {"env": "ELEVENST_API_KEY", "label": "API Key", "secret": True, "required": True},
        {"env": "ELEVENST_DISP_CTGR_NO", "label": "기본 카테고리 번호 (선택)", "secret": False, "required": False},
    ],
    "shopify": [
        {"env": "SHOPIFY_SHOP", "label": "상점 도메인 (xxx.myshopify.com)", "secret": False, "required": True},
        {"env": "SHOPIFY_AUTO_TOKEN", "label": "Admin API access token (shpat_…)", "secret": True, "required": True},
        {"env": "SHOPIFY_CLIENT_SECRET", "label": "Client Secret (선택)", "secret": True, "required": False},
    ],
    "woocommerce": [
        {"env": "WC_URL", "label": "사이트 URL", "secret": False, "required": True},
        {"env": "WC_KEY", "label": "Consumer Key", "secret": True, "required": True},
        {"env": "WC_SECRET", "label": "Consumer Secret", "secret": True, "required": True},
    ],
}

# 마켓 표시명
MARKET_LABELS = {
    "coupang": "쿠팡",
    "smartstore": "스마트스토어",
    "elevenst": "11번가",
    "shopify": "Shopify",
    "woocommerce": "WooCommerce",
}

SUPPORTED_MARKETS = list(MARKET_CRED_FIELDS.keys())


def _safe_seller_id(seller_id: str) -> str:
    sid = re.sub(r"[^A-Za-z0-9_.@-]", "_", str(seller_id or "default")).strip("_") or "default"
    return sid[:128]


def _fernet():
    """Fernet 인스턴스 반환 (암호화 불가 환경이면 None)."""
    try:
        from cryptography.fernet import Fernet
    except Exception:  # pragma: no cover - cryptography 미설치
        return None

    raw = os.getenv("MARKET_CRED_ENC_KEY")
    if raw:
        try:
            return Fernet(raw.encode() if isinstance(raw, str) else raw)
        except Exception:
            logger.warning("MARKET_CRED_ENC_KEY 형식 오류 — SECRET_KEY 파생으로 폴백")

    secret = os.getenv("SECRET_KEY")
    if secret:
        key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
        return Fernet(key)
    return None


def _path(seller_id: str) -> str:
    return os.path.join(_DATA_DIR, f"{_safe_seller_id(seller_id)}.json")


def _load_all(seller_id: str) -> Dict[str, Dict[str, str]]:
    path = _path(seller_id)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fp:
            blob = json.load(fp)
    except Exception as exc:
        logger.warning("자격증명 로드 실패(%s): %s", path, exc)
        return {}

    if not isinstance(blob, dict):
        return {}
    if blob.get("_enc"):
        fernet = _fernet()
        if not fernet:
            logger.warning("암호화된 자격증명이나 복호화 키 없음 — 빈 값 반환")
            return {}
        try:
            decrypted = fernet.decrypt(str(blob.get("data", "")).encode()).decode("utf-8")
            data = json.loads(decrypted)
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            logger.warning("자격증명 복호화 실패: %s", exc)
            return {}
    data = blob.get("data")
    return data if isinstance(data, dict) else {}


def _save_all(seller_id: str, data: Dict[str, Dict[str, str]]) -> None:
    os.makedirs(_DATA_DIR, exist_ok=True)
    path = _path(seller_id)
    fernet = _fernet()
    if fernet:
        token = fernet.encrypt(json.dumps(data, ensure_ascii=False).encode("utf-8")).decode("utf-8")
        blob = {"_enc": True, "data": token}
    else:
        logger.warning("암호화 키 없음 — 자격증명을 평문으로 저장합니다(개발용). 운영에서는 MARKET_CRED_ENC_KEY를 설정하세요.")
        blob = {"_enc": False, "data": data}
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fp:
        json.dump(blob, fp, ensure_ascii=False)
    os.replace(tmp, path)


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def get(seller_id: str, market: str) -> Dict[str, str]:
    """셀러의 특정 마켓 자격증명(환경변수 이름→값) 반환."""
    return dict(_load_all(seller_id).get(market, {}))


def save(seller_id: str, market: str, values: Dict[str, str]) -> Dict[str, str]:
    """알려진 필드만 추려 저장한다. 빈 값은 제외. 저장된 값 반환."""
    if market not in MARKET_CRED_FIELDS:
        raise KeyError(market)
    allowed = {f["env"] for f in MARKET_CRED_FIELDS[market]}
    cleaned = {
        env: str(val).strip()
        for env, val in (values or {}).items()
        if env in allowed and str(val).strip()
    }
    data = _load_all(seller_id)
    # 병합: 입력한 필드만 갱신하고 나머지(예: 비워둔 비밀값)는 기존 값 유지.
    existing = data.get(market) if isinstance(data.get(market), dict) else {}
    merged = {**existing, **cleaned}
    data[market] = merged
    _save_all(seller_id, data)
    return merged


def delete(seller_id: str, market: str) -> bool:
    """셀러의 특정 마켓 자격증명을 삭제한다."""
    data = _load_all(seller_id)
    if market in data:
        del data[market]
        _save_all(seller_id, data)
        return True
    return False


def credential_env(seller_id: str, market: str) -> Dict[str, str]:
    """주입용 환경변수 dict (셀러 저장값만). 없으면 빈 dict."""
    return get(seller_id, market)


def all_credential_env(seller_id: str) -> Dict[str, str]:
    """셀러가 저장한 모든 마켓 자격증명을 하나로 합친 env dict.

    마켓별 env 이름은 서로 겹치지 않으므로 단순 병합으로 안전하다.
    진단/현황 화면이 셀러 저장 키를 반영하도록 주입할 때 사용.
    """
    merged: Dict[str, str] = {}
    for market_values in _load_all(seller_id).values():
        if isinstance(market_values, dict):
            merged.update({k: v for k, v in market_values.items() if v})
    return merged


def is_connected(seller_id: str, market: str) -> bool:
    """필수 필드가 셀러 저장값 또는 전역 환경변수로 모두 채워졌는지."""
    if market not in MARKET_CRED_FIELDS:
        return False
    stored = get(seller_id, market)
    for field in MARKET_CRED_FIELDS[market]:
        if not field.get("required"):
            continue
        if not (stored.get(field["env"]) or os.getenv(field["env"])):
            return False
    return True


def _mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 4:
        return "••••"
    return value[:2] + "••••" + value[-2:]


def status(seller_id: str, market: str) -> Dict[str, Any]:
    """화면 표시용 상태 (마스킹된 값 포함, 비밀값 노출 금지)."""
    stored = get(seller_id, market)
    fields = []
    for field in MARKET_CRED_FIELDS.get(market, []):
        env = field["env"]
        stored_val = stored.get(env, "")
        global_val = os.getenv(env, "")
        has_value = bool(stored_val or global_val)
        display = ""
        if stored_val:
            display = _mask(stored_val) if field.get("secret") else stored_val
        elif global_val:
            display = "(서버 환경변수)" if field.get("secret") else global_val
        fields.append({
            "env": env,
            "label": field["label"],
            "secret": field.get("secret", False),
            "required": field.get("required", False),
            "has_value": has_value,
            "from_global": bool(global_val and not stored_val),
            "display": display,
        })
    return {
        "market": market,
        "label": MARKET_LABELS.get(market, market),
        "connected": is_connected(seller_id, market),
        "has_seller_credentials": bool(stored),
        "fields": fields,
    }


def all_status(seller_id: str) -> List[Dict[str, Any]]:
    return [status(seller_id, m) for m in SUPPORTED_MARKETS]


@contextmanager
def temp_env(updates: Dict[str, Optional[str]]):
    """주어진 환경변수를 일시 주입하고 종료 시 원복한다 (빈 값/None은 건너뜀)."""
    applied = {k: v for k, v in (updates or {}).items() if v}
    original = {name: os.environ.get(name) for name in applied}
    try:
        for name, value in applied.items():
            os.environ[name] = value
        yield
    finally:
        for name, value in original.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


@contextmanager
def seller_market_env(seller_id: str, markets, extra: Optional[Dict[str, str]] = None):
    """선택 마켓들의 셀러 자격증명을 환경변수에 일시 주입한다.

    셀러 저장값이 있으면 그것으로, 없으면 기존 전역 환경변수를 그대로 사용.
    `extra`로 입력 중(미저장) 값을 추가 주입할 수 있다. 종료 시 원래 값으로 복원.
    """
    if isinstance(markets, str):
        markets = [markets]
    updates: Dict[str, str] = {}
    for market in markets or []:
        updates.update(credential_env(seller_id, market))
    if extra:
        updates.update({k: v for k, v in extra.items() if v})

    with temp_env(updates):
        yield

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
        # 📦 출고지·반품지 — 상품 등록 시 쿠팡이 필수로 요구(없으면 등록 거부). 한 번만 입력하면 됨.
        {"env": "COUPANG_VENDOR_USER_ID", "label": "Wing 로그인 ID", "secret": False, "required": False,
         "section": "📦 출고지·반품지 정보 — 상품 등록에 필수 (한 번만 입력하면 모든 등록에 자동 사용)",
         "help": "쿠팡 윙에 로그인할 때 쓰는 아이디(이메일/ID). Vendor ID(A+숫자)와 다릅니다."},
        {"env": "COUPANG_OUTBOUND_SHIPPING_PLACE_CODE", "label": "출고지 코드", "secret": False, "required": False,
         "help": "쿠팡 윙 → 판매자정보 → 배송정보(출고지/반품지) → ‘출고지’의 코드(숫자). 예: 7437895"},
        {"env": "COUPANG_RETURN_CENTER_CODE", "label": "반품지센터코드", "secret": False, "required": False,
         "help": "쿠팡 윙 → 배송정보 → ‘반품지’의 센터코드(숫자). 예: 1000274592"},
        {"env": "COUPANG_RETURN_ZIP_CODE", "label": "반품지 우편번호", "secret": False, "required": False,
         "help": "반품지 주소의 우편번호 5자리. 예: 06236"},
        {"env": "COUPANG_RETURN_ADDRESS", "label": "반품지 주소", "secret": False, "required": False,
         "help": "반품을 받을 기본주소. 예: 서울특별시 강남구 테헤란로 123"},
        {"env": "COUPANG_RETURN_ADDRESS_DETAIL", "label": "반품지 상세주소 (선택)", "secret": False, "required": False,
         "help": "동·호수 등 상세주소. 예: 4층 101호"},
        {"env": "COUPANG_RETURN_CHARGE_NAME", "label": "반품지 담당자명", "secret": False, "required": False,
         "help": "반품을 받는 담당자명 또는 상호. 예: 코가네CS"},
        {"env": "COUPANG_COMPANY_CONTACT_NUMBER", "label": "반품지 연락처", "secret": False, "required": False,
         "help": "반품 문의 전화번호. 예: 02-123-4567"},
        {"env": "COUPANG_RETURN_CHARGE", "label": "반품배송비 (선택, 기본 5000원)", "secret": False, "required": False,
         "help": "편도 반품배송비(원). 비워두면 5000원으로 자동 설정됩니다."},
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
        {"env": "SHOPIFY_CLIENT_ID", "label": "Client ID", "secret": False, "required": True},
        {"env": "SHOPIFY_CLIENT_SECRET", "label": "Client Secret (shpss_…)", "secret": True, "required": True},
        {"env": "SHOPIFY_AUTO_TOKEN", "label": "직접 토큰 (shpat_, 선택)", "secret": True, "required": False},
    ],
    "woocommerce": [
        {"env": "WC_URL", "label": "사이트 URL", "secret": False, "required": True},
        {"env": "WC_KEY", "label": "Consumer Key", "secret": True, "required": True},
        {"env": "WC_SECRET", "label": "Consumer Secret", "secret": True, "required": True},
    ],
    # K2 — **연동대행사 모델**(톡스토어). 다른 마켓과 축이 다르다:
    #   대행사 앱 Admin키는 **서버 비밀 1개**(env — 이 표에 없다), 판매자는 **자기 인증키만** 넣는다.
    #   그래서 필드가 둘뿐이고 Admin키는 이 화면에 절대 나오지 않는다(계약이 검사).
    "talkstore": [
        {"env": "TALKSTORE_SELLER_API_KEY", "label": "판매자 API 인증키", "secret": True,
         "required": True,
         "section": "🔗 연동대행사 방식 — 고가브릿지가 대행사로 등록돼 있어야 동작합니다",
         "help": "톡스토어 판매자센터에서 발급한 본인 API 인증키. 대행사 앱 키는 저희 서버가 "
                 "갖고 있어 따로 넣지 않으셔도 됩니다."},
        {"env": "TALKSTORE_STORE_ID", "label": "스토어 ID", "secret": False, "required": False,
         "help": "매핑 대상 스토어를 구분할 때 씁니다(있으면 입력)."},
    ],
}

# 마켓 표시명
MARKET_LABELS = {
    "coupang": "쿠팡",
    "smartstore": "스마트스토어",
    "elevenst": "11번가",
    "shopify": "Shopify",
    "woocommerce": "WooCommerce",
    "talkstore": "톡스토어",
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


def _pg_links():
    """Postgres 이관 백엔드 활성 시 market_links_pg 반환(스키마 1회), 아니면 None(data/ 파일 폴백)."""
    try:
        from src.db import pg as _pgmod
        if _pgmod.pg_enabled():
            _pgmod.init_schema()
            from src.db import market_links_pg as _ml
            return _ml
    except Exception as exc:
        logger.warning("PG 연동정보 백엔드 확인 실패 — data/ 폴백: %s", exc)
    return None


def _path(seller_id: str) -> str:
    return os.path.join(_DATA_DIR, f"{_safe_seller_id(seller_id)}.json")


def _load_all(seller_id: str) -> Dict[str, Dict[str, str]]:
    _b = _pg_links()
    if _b is not None:
        return _b.load_all(seller_id)
    return load_all_from_file(seller_id)


def load_all_from_file(seller_id: str) -> Dict[str, Dict[str, str]]:
    """data/<seller>.json에서 직접 로드(복호화) — 이관 스크립트가 PG 활성 시에도 원본을 읽게."""
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
    _b = _pg_links()
    if _b is not None:
        return _b.save(seller_id, market, merged)     # PG: (user_id,market) upsert(암호문)
    data[market] = merged
    _save_all(seller_id, data)
    return merged


def delete(seller_id: str, market: str) -> bool:
    """셀러의 특정 마켓 자격증명을 삭제한다."""
    _b = _pg_links()
    if _b is not None:
        return _b.delete(seller_id, market)
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


def _market_ok(stored: Dict[str, str], market: str) -> bool:
    fields = MARKET_CRED_FIELDS.get(market)
    if not fields:
        return False
    for field in fields:
        if not field.get("required"):
            continue
        if not ((stored or {}).get(field["env"]) or os.getenv(field["env"])):
            return False
    return True


def is_connected(seller_id: str, market: str) -> bool:
    """필수 필드가 셀러 저장값 또는 전역 환경변수로 모두 채워졌는지."""
    if market not in MARKET_CRED_FIELDS:
        return False
    return _market_ok(get(seller_id, market), market)


def connected_markets(seller_id: str, markets) -> Dict[str, bool]:
    """v51 STEP2: 여러 마켓의 연결 여부를 **_load_all 1회**로 판정(드로어의 5회 왕복 → 1회).

    is_connected를 마켓마다 부르면 _load_all(=PG 쿼리)이 N번 → 대륙 간 RTT가 N배. 한 번 읽어 메모리에서 판정.
    """
    alld = _load_all(seller_id)
    return {m: _market_ok(alld.get(m, {}), m) for m in markets}


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
            "help": field.get("help", ""),
            "section": field.get("section", ""),
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

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

# F34-1: **못 읽은 것과 없는 것은 다른 사건이다.** 복호화가 실패하면 예전엔 조용히 `{}`였고,
#   그 빈 dict가 화면·사전검증을 지나 「입력한 적 없음」처럼 보였다(오너 실측 2026-09-19:
#   6칸을 넣고 저장했는데 검증기는 7칸 전부 「비어 있음」이라고 했다).
_FILE_READ_ERROR: dict = {}


# 마켓별 입력 필드 정의 (env = 코드가 실제로 읽는 표준 환경변수 이름).
# secret=True 인 값은 화면에 마스킹해서 표시한다.
MARKET_CRED_FIELDS: Dict[str, List[Dict[str, Any]]] = {
    "coupang": [
        {"env": "COUPANG_ACCESS_KEY", "label": "Access Key", "secret": True, "required": True},
        {"env": "COUPANG_SECRET_KEY", "label": "Secret Key", "secret": True, "required": True},
        {"env": "COUPANG_VENDOR_ID", "label": "Vendor ID", "secret": False, "required": True},
        # 📦 출고지·반품지 — 상품 등록 시 쿠팡이 필수로 요구(없으면 등록 거부). 한 번만 입력하면 됨.
        {"env": "COUPANG_VENDOR_USER_ID", "label": "Wing 로그인 ID", "secret": False, "required": False,
         "section": "출고지·반품지 정보 — 상품 등록에 필수 (한 번만 입력하면 모든 등록에 자동 사용)",
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

# S1 — 화면마다 다른 마켓 코드를 쓰던 것을 여기서 흡수한다.
#   실측: `/seller/markets`는 `11st`, `/markets/connect`는 `elevenst`를 썼고, 같은 마켓인데
#   판정이 갈렸다(11번가 키가 있어도 한쪽은 False). 표준은 **elevenst**, 나머지는 별칭.
MARKET_ALIASES = {"11st": "elevenst", "eleven": "elevenst", "naver": "smartstore",
                  "naver_commerce": "smartstore", "woo": "woocommerce", "wc": "woocommerce"}


def canonical_market(market: str) -> str:
    """마켓 코드 표준형. 모르는 코드는 그대로 돌려준다(조용히 바꾸지 않는다)."""
    m = str(market or "").strip().lower()
    return MARKET_ALIASES.get(m, m)


def credential_source(seller_id: str, market: str) -> str:
    """자격이 **어디서** 왔나 — "seller"(내 키) / "server"(서버 설정) / ""(없음).

    화면이 '연결됨'만 보여주면 셀러는 자기가 넣은 건지 서버가 갖고 있는 건지 모른다.
    판정(연결 여부)과 출처는 **다른 질문**이라 따로 답한다.
    """
    market = canonical_market(market)
    fields = MARKET_CRED_FIELDS.get(market) or []
    if not fields:
        return ""
    stored = _load_all(seller_id).get(market) or {}
    required = [f["env"] for f in fields if f.get("required")] or [f["env"] for f in fields]
    if any(str(stored.get(env, "") or "").strip() for env in required):
        return "seller"
    if any(str(os.getenv(env, "") or "").strip() for env in required):
        return "server"
    return ""


SOURCE_LABEL = {"seller": "내 키", "server": "서버 설정", "": "미설정"}


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


def backend_state() -> Dict[str, Any]:
    """어느 저장소에 쓰고 읽는가 — `{backend, degraded, reason}` (F34-1).

    ## 왜 이걸 따로 묻나

    `pg.pg_enabled()`는 **워커 수명 동안 첫 접속 결과를 캐시한다.** 그래서 접속이 한 번
    삐끗한 워커는 그 뒤로 계속 `data/<seller>.json`에 쓴다 — 그 파일은 Render에서
    **컨테이너와 함께 사라지고, 옆 워커에는 보이지도 않는다.**

    그러면 셀러 화면엔 「저장됨」이 뜨고, 다음 요청(다른 워커)에서 사전검증은 「비어 있음」이
    된다. 오너가 6칸을 넣고 저장했는데 7칸 전부 비었다고 나온 그 모양이다.

    > ★ **운영에서 DATABASE_URL이 있는데 PG로 못 가면, 파일에 쓰는 것은 저장이 아니라 거짓말이다.**
    > (같은 판정을 F30이 이미 이미지 저장소에 적용했다 — 여기만 예외일 이유가 없다.)
    """
    try:
        from src.db import pg as _pgmod
        url = (_pgmod.db_url() or "").strip()
        if not url:
            return {"backend": "file", "degraded": False, "reason": ""}
        if _pgmod.pg_enabled():
            return {"backend": "pg", "degraded": False, "reason": ""}
        return {"backend": "file", "degraded": True,
                "reason": "DB(Postgres)에 연결하지 못했습니다 — 지금 저장하면 "
                          "재시작 때 사라지고 다른 워커에는 보이지 않습니다"}
    except Exception as exc:
        return {"backend": "file", "degraded": True,
                "reason": f"저장소 상태를 확인하지 못했습니다: {type(exc).__name__}"}


def _path(seller_id: str) -> str:
    return os.path.join(_DATA_DIR, f"{_safe_seller_id(seller_id)}.json")


def _load_all(seller_id: str) -> Dict[str, Dict[str, str]]:
    _b = _pg_links()
    if _b is not None:
        return _b.load_all(seller_id)
    return load_all_from_file(seller_id)


def load_all_from_file(seller_id: str) -> Dict[str, Dict[str, str]]:
    """data/<seller>.json에서 직접 로드(복호화) — 이관 스크립트가 PG 활성 시에도 원본을 읽게."""
    _FILE_READ_ERROR.clear()
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
            _FILE_READ_ERROR.update({
                "reason": "암호화된 값인데 복호화 키가 없습니다"
                          "(MARKET_CRED_ENC_KEY 또는 SECRET_KEY 확인)"})
            logger.warning("암호화된 자격증명이나 복호화 키 없음 — 빈 값 반환")
            return {}
        try:
            decrypted = fernet.decrypt(str(blob.get("data", "")).encode()).decode("utf-8")
            data = json.loads(decrypted)
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            _FILE_READ_ERROR.update({"reason": f"복호화 실패: {type(exc).__name__}"})
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


def unknown_fields(market: str, values: Dict[str, str]) -> List[str]:
    """이 마켓에 **없는 칸 이름** — 조용히 버리지 않고 이름을 돌려준다 (F34-1)."""
    allowed = {f["env"] for f in MARKET_CRED_FIELDS.get(canonical_market(market), [])}
    return sorted(k for k, v in (values or {}).items()
                  if k not in allowed and str(v or "").strip())


def save(seller_id: str, market: str, values: Dict[str, str]) -> Dict[str, str]:
    """알려진 필드만 추려 저장한다. 빈 값은 제외. 저장된 값 반환.

    ## F34-1 — 저장은 **다시 읽힐 때** 저장이다

    오너 실측(2026-09-19): 드로어에 여섯 칸을 넣고 저장했는데, 다음 날 드로어를 다시 여니
    **여섯 칸이 전부 비어 있었다**(유일하게 차 있던 Wing ID는 저장값이 아니라 제안이었다).
    화면은 「저장했어요」라고 했다.

    쓰기가 어디로 갔든 — 사라질 파일이든, 못 읽을 암호문이든, 아무 칸도 안 남은
    빈 병합이든 — **되읽어서 없으면 그건 저장이 아니다.** 그러면 실패라고 말한다.
    (같은 규율을 수집 이력이 STEP 1-0에서 이미 쓴다 — write-then-verify.)
    """
    if market not in MARKET_CRED_FIELDS:
        raise KeyError(market)
    allowed = {f["env"] for f in MARKET_CRED_FIELDS[market]}
    cleaned = {
        env: str(val).strip()
        for env, val in (values or {}).items()
        if env in allowed and str(val).strip()
    }
    # 보낸 값이 **전부** 이 마켓에 없는 이름이면, 아무것도 안 하고 「저장됨」이라 하지 않는다.
    if (values or {}) and not cleaned:
        bad = unknown_fields(market, values)
        raise ValueError("저장할 값이 없습니다"
                         + (f" — 이 마켓에 없는 칸: {', '.join(bad)}" if bad else
                            " — 보낸 값이 모두 비어 있습니다"))
    data = _load_all(seller_id)
    # 병합: 입력한 필드만 갱신하고 나머지(예: 비워둔 비밀값)는 기존 값 유지.
    existing = data.get(market) if isinstance(data.get(market), dict) else {}
    merged = {**existing, **cleaned}
    _b = _pg_links()
    if _b is not None:
        saved = _b.save(seller_id, market, merged)     # PG: (user_id,market) upsert(암호문)
    else:
        # F34-1: **폴백 저장은 성공이 아니다.** DATABASE_URL이 있는데 PG로 못 갔다면, 파일에
        #   써 봐야 다음 요청(다른 워커)에선 없다 — 화면엔 「저장됨」, 검증기엔 「비어 있음」.
        _bs = backend_state()
        if _bs.get("degraded"):
            raise RuntimeError(_bs.get("reason") or "자격 저장소에 연결하지 못했습니다")
        data[market] = merged
        _save_all(seller_id, data)
        saved = merged
    _verify_saved(seller_id, market, cleaned)
    return saved


def _verify_saved(seller_id: str, market: str, cleaned: Dict[str, str]) -> None:
    """쓴 값을 **되읽는다.** 안 보이면 실패다 — 사유를 문장에 싣고 올린다 (F34-1)."""
    if not cleaned:
        return
    try:
        back = get(seller_id, market)
    except Exception as exc:                 # 되읽기 자체가 터졌다 = 저장 확인 불가
        raise RuntimeError(f"저장 뒤 확인에 실패했습니다: {type(exc).__name__}") from exc
    gone = sorted(env for env, val in cleaned.items() if str(back.get(env, "")) != val)
    if not gone:
        return
    why = read_state(seller_id)
    raise RuntimeError(
        f"저장한 값이 다시 읽히지 않습니다({len(gone)}칸: {', '.join(gone)})"
        + (f" — {why.get('reason')}" if not why.get("ok") else ""))


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


def read_state(seller_id: str = "") -> Dict[str, Any]:
    """저장된 자격을 **읽을 수 있었나**. `{ok, reason}` (F34-1).

    화면·사전검증이 「비어 있음」이라 말하기 전에 **이걸 먼저 묻는다.**
    못 읽은 것을 「없다」고 말하면, 사람은 이미 넣어 둔 값을 또 넣는다(오너가 실제로 그랬다).
    """
    _bs = backend_state()
    if _bs.get("degraded"):
        return {"ok": False, "reason": str(_bs.get("reason") or "저장소 상태 미상")}
    _b = _pg_links()
    if _b is not None:
        try:
            err = _b.last_read_error()
        except Exception:
            err = {}
    else:
        err = dict(_FILE_READ_ERROR)
    if err.get("reason"):
        return {"ok": False, "reason": str(err["reason"])}
    return {"ok": True, "reason": ""}


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
    """필수 필드가 셀러 저장값 또는 전역 환경변수로 모두 채워졌는지.

    ★ S1 — **연결 판정의 단일 소스**. 다른 화면이 자기 판정을 따로 만들지 않는다
    (계약 `test_s1_single_connection_judge`가 판정기 2개 존재를 금지한다).
    """
    market = canonical_market(market)
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


def _suggest_value(env: str) -> str:
    """빈 칸에 미리 채워 줄 값 — **아는 것만**. 모르면 빈 문자열(추측 0).

    F29: 오너가 채워야 할 칸을 줄이는 게 목적이다. 다만 **이 서버의 자격이 오너 계정일 때만**
    제안한다 — 모르는 업체코드면 아무것도 제안하지 않는다(남의 Wing 아이디를 남의 칸에
    채우지 않는다).

    F32-3 실측: 처음엔 `resolve_upload_account()`로 물었는데, 그건 「**어느 이름으로 읽나**」다.
    오너 Render엔 접두와 무접두가 **둘 다** 있어 그 답이 `""`였고, 제안이 통째로 사라졌다.
    물어야 할 것은 「이 자격이 **누구 것인가**」 — `business_account()`가 그 질문이다
    (무접두여도 업체코드로 사업체를 안다).
    """
    if env != "COUPANG_VENDOR_USER_ID":
        return ""
    try:
        from src.seller_console.market_cred_view import WING_USER_IDS, business_account
        return WING_USER_IDS.get(business_account(), "")
    except Exception:
        return ""


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
            # F29: 아는 값은 **미리 채워 둔다**(비어 있는 칸에 한해). 사람이 고칠 수 있고,
            #   고친 값을 상수가 덮지 않는다. 비밀값엔 절대 제안을 붙이지 않는다.
            "suggest": ("" if (has_value or field.get("secret"))
                        else _suggest_value(env)),
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

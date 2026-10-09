"""Y7-H(오너 2026-10-09 19:46 KST) — 네이버 상품정보제공고시(`productInfoProvidedNotice`) 한 곳.

증거: 셰고가 플리츠 세트 등록 400 invalidInputs
  - `productInfoProvidedNotice.etc.itemName` — 품명 50자 미만(우리는 「[해외직구] + 상품명」을 100자에서 잘라 보냈다)
  - `productInfoProvidedNotice.etc.manufacturer` — 제조자 입력(수집 브랜드가 비어 빈칸으로 보냈다)
네이버 400을 한 칸씩 받는 방식을 끝낸다 — 타입별로 문서에 있는 칸을 **전부** 채운다.

타입(카테고리 경로로 고른다)
  - 「패션의류」 → `WEAR`(의류) · 그 밖 → `ETC`(기타 재화 — 정본 템플릿이 가방 카테고리에서 이 타입으로 통과한 이력)
  - 문서의 다른 타입(신발·가방·화장품…)은 칸별 필수 표시를 원문으로 확인하지 못해 아직 쓰지 않는다(짐작 금지 — ETC로 보낸다).

구매대행 기본값(설정 화면 「네이버 상품정보제공고시」에서 바꾼다)
  - 품명·모델명: 등록상품명(쿠팡용 짧은 이름) — 문서 상한 50자. **자르지 않는다**: 짧은 이름 중 50자 이내 것을 쓰고,
    없으면 비워 두어 사전검증이 `naver_required_itemName`으로 보류한다.
  - 제조자/수입자: 수집 브랜드(있으면 — 사실), 없으면 「상세페이지 참조」 + 제조국(중국 소싱처일 때 기본 「중국」)
  - 소재·색상·치수·세탁방법·제조연월·품질보증기준: 「상세페이지 참조」
  - A/S 책임자·전화: 스토어별 `NAVER_AS_PHONE`(계정 env — 셀러 CS 연락처 설정이 아직 이 자리)
  - KC 인증(기타 재화의 인증 칸): 구매대행 고지 문구(`PURCHASE_AGENT_NOTICE`)와 같은 글
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

ITEM_NAME_MAX = 50          # 문서: itemName·modelName ≤ 50자
TEXT_MAX = 200              # 문서: manufacturer·color·size·afterServiceDirector ≤ 200자
LONG_MAX = 1500             # 문서: caution·warrantyPolicy ≤ 1500자
CERT_MAX = 500              # 문서: certificateDetails ≤ 500자

#: 설정 칸 — (열쇠, 화면 이름, 기본값). 「상세페이지 참조」는 구매대행 관행(오너 2026-10-09).
SETTING_FIELDS = (
    ("detail_ref", "상세페이지 참조 문구", "상세페이지 참조"),
    ("manufacturer", "제조자/수입자", "상세페이지 참조"),
    ("origin_cn", "제조국(중국 소싱처)", "중국"),
    ("return_cost_reason", "반품 비용 기준", "단순변심 왕복배송비"),
    ("no_refund_reason", "청약철회 불가 사유", "개봉후 단순변심 반품불가"),
    ("quality_standard", "품질보증기준", "소비자분쟁해결기준"),
    ("compensation", "대금 환불·지연 보상", "고객센터 협의"),
    ("trouble_shooting", "소비자 피해 보상·분쟁 처리", "고객센터 협의"),
)
DEFAULTS = {k: v for k, _label, v in SETTING_FIELDS}
_KEY = "naver_notice:"

_CN_HOSTS = re.compile(r"(taobao|tmall|1688|alicdn|aliexpress|jd\.com|pinduoduo|yangkeduo|vvic|temu)", re.I)


# ── 설정(공유 마켓 사용자는 한 벌, 그 밖은 셀러별 — 배송 설정과 같은 범위) ─────────────────────────────

def _scope(seller_id: str = "", shared: Optional[bool] = None) -> str:
    if shared is None:
        try:
            from src.seller_console.shipping_ratio import _session_shared
            shared = _session_shared()
        except Exception:
            shared = False
    return "shared" if shared else str(seller_id or "default")


def get_settings(seller_id: str = "", shared: Optional[bool] = None) -> Dict[str, str]:
    out = dict(DEFAULTS)
    try:
        from src.db import image_translate_queue_pg as st
        saved = st.state_get(_KEY + _scope(seller_id, shared)) or {}
        out.update({k: str(v).strip() for k, v in saved.items() if k in DEFAULTS and str(v or "").strip()})
    except Exception as exc:                                     # noqa: BLE001 — 기본값으로
        logger.debug("[네이버 고시] 설정 읽기 실패(기본값): %s", exc)
    return out


def save_settings(seller_id: str, values: Dict[str, Any], shared: Optional[bool] = None) -> Dict[str, str]:
    new = {}
    for k, label, _d in SETTING_FIELDS:
        v = str((values or {}).get(k) or "").strip()
        if len(v) > TEXT_MAX:
            raise ValueError(f"「{label}」은 {TEXT_MAX}자까지예요({len(v)}자)")
        if v:
            new[k] = v
    from src.db import image_translate_queue_pg as st
    st.state_set(_KEY + _scope(seller_id, shared), new)
    return get_settings(seller_id, shared)


# ── 타입·값 ───────────────────────────────────────────────────────────────────────────────

def notice_type(category_path: str) -> str:
    """카테고리 경로 → 고시 타입. 「패션의류>…」 = WEAR, 그 밖(경로 모름 포함) = ETC."""
    top = str(category_path or "").split(">")[0].strip()
    return "WEAR" if top == "패션의류" else "ETC"


def category_path(product: Dict[str, Any]) -> str:
    try:
        from src.uploaders import naver_categories as _nc
        return _nc.name_of(str(product.get("category_id") or product.get("naver_category_id") or ""))
    except Exception:
        return ""


def short_name(product: Dict[str, Any]) -> str:
    """품명·모델명 — 50자 이내의 **짧은 이름**(자르지 않는다). 등록상품명(쿠팡용) → 한국어 상품명 순. 없으면 ''."""
    for k in ("coupang_name", "title_ko", "title"):
        v = re.sub(r"\s+", " ", str(product.get(k) or "")).strip()
        v = re.sub(r"^\[해외직구\]\s*", "", v)                       # 네이버 상품명 접두는 품명이 아니다
        v = _unmark(v)                                              # Y7-J: 고시 칸에도 상표 이름을 싣지 않는다
        if v and len(v) <= ITEM_NAME_MAX:
            return v
    return ""


def _unmark(text: str) -> str:
    """Y7-J(오너 2026-10-10) — 상표 게이트(제목과 같은 표: 「미야케」 등)를 고시 칸에도. 이름만 지운다."""
    try:
        from src.collectors.ko_polish import strip_marks
        return strip_marks(text)[0]
    except Exception:
        return str(text or "")


def origin_text(product: Dict[str, Any], st: Dict[str, str]) -> str:
    src = " ".join(str(product.get(k) or "") for k in ("source_url", "url", "source"))
    imgs = " ".join(str(u) for u in (product.get("images") or [])[:1])
    return st["origin_cn"] if _CN_HOSTS.search(src + " " + imgs) else st["detail_ref"]


def build(product: Dict[str, Any], *, as_phone: str = "", settings: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """`productInfoProvidedNotice` 통째(타입 + 그 타입 블록 하나). 채울 수 없는 칸은 빈 문자열(사전검증이 보류)."""
    st = settings or get_settings()
    ref = st["detail_ref"]
    common = {
        "returnCostReason": st["return_cost_reason"],
        "noRefundReason": st["no_refund_reason"],
        "qualityAssuranceStandard": st["quality_standard"],
        "compensationProcedure": st["compensation"],
        "troubleShootingContents": st["trouble_shooting"],
    }
    origin = origin_text(product, st)
    # 수집 브랜드가 있으면 그게 제조자(사실) — 없을 때만 「상세페이지 참조」(19:46 KST 400: 브랜드 빈칸으로 빈 제조자)
    who = _unmark(str(product.get("brand") or "").strip()) or st["manufacturer"]
    maker = who if origin == ref else f"{who} (제조국: {origin})"
    phone = str(as_phone or "").strip()
    t = notice_type(category_path(product))
    if t == "WEAR":
        block = {**common,
                 "material": ref, "color": ref, "size": ref,
                 "manufacturer": maker[:TEXT_MAX],
                 "caution": ref, "packDateText": ref,
                 "warrantyPolicy": st["quality_standard"][:LONG_MAX],
                 "afterServiceDirector": phone[:TEXT_MAX]}
        return {"productInfoProvidedNoticeType": "WEAR", "wear": block}
    name = short_name(product)
    from src.seller_console.notice_texts import PURCHASE_AGENT_NOTICE
    block = {**common,
             "itemName": name, "modelName": name,
             "manufacturer": maker[:TEXT_MAX],
             "certificateDetails": PURCHASE_AGENT_NOTICE[:CERT_MAX],
             "afterServiceDirector": phone[:TEXT_MAX]}
    return {"productInfoProvidedNoticeType": "ETC", "etc": block}


#: 타입별 필수 칸(Context7 `/websites/apicenter_commerce_naver` 원상품 정보 구조체 요약 — 원문 표 확인 불가, 문서에 나온 칸 전부).
REQUIRED = {
    "WEAR": ("returnCostReason", "noRefundReason", "qualityAssuranceStandard", "compensationProcedure",
             "troubleShootingContents", "material", "color", "size", "manufacturer", "caution", "packDateText",
             "warrantyPolicy", "afterServiceDirector"),
    "ETC": ("returnCostReason", "noRefundReason", "qualityAssuranceStandard", "compensationProcedure",
            "troubleShootingContents", "itemName", "modelName", "manufacturer", "afterServiceDirector"),
}
LIMITS = {"itemName": ITEM_NAME_MAX, "modelName": ITEM_NAME_MAX}


def missing(notice: Dict[str, Any]) -> List[str]:
    """빈 칸·길이 초과 칸 이름 — 사전검증 `naver_required_<칸>`."""
    t = str((notice or {}).get("productInfoProvidedNoticeType") or "")
    block = (notice or {}).get(t.lower()) or {}
    out = []
    for f in REQUIRED.get(t, ()):
        v = str(block.get(f) or "").strip()
        if not v or len(v) > LIMITS.get(f, 10 ** 6):
            out.append(f)
    return out

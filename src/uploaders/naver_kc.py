"""Y13-G 1(오너 2026-10-20) — 네이버 KC 인증 대상 카테고리 · 구매대행 KC 특례.

실측(10-20 06:30 UTC BLACKHOLES 셰고가·고코스모스 · 카테고리 벽등 50003332): 400
`originProduct.detailAttribute.productCertificationInfos — KC 인증대상 인증 종류를 선택하셔야 합니다`.
우리는 템플릿 그대로 `certificationTargetExcludeContent: {}`(= `kcCertifiedProductExclusionYn` 기본 FALSE · KC 인증 대상)를 보냈다.

출처(문서 원문 — 커머스API 공식 기술지원 GitHub 토론 #704 「상품 정보 내 인증 정보 수록 방법」, 관리자 작성):
- 카테고리 조회 `GET /v1/categories/:categoryId` 응답 `exceptionalCategories`에 `KC_CERTIFICATION`이 있으면
  「대상 카테고리에 상품 등록/수정 시 KC인증 정보를 요구합니다」.
- `certificationTargetExcludeContent.kcCertifiedProductExclusionYn`: "TRUE"(대상 아님) · "FALSE"(대상 · 기본) ·
  "KC_EXEMPTION_OBJECT"(KC인증 특례 대상 — `kcExemptionType` 필요).
- `kcExemptionType`: "OVERSEAS"(구매대행) · "SAFE_CRITERION" · "PARALLEL_IMPORT".
- 「단, 상품이 부여받은 인증 정보가 없다면 KC인증 종류의 인증 정보 미구성으로도 상품 등록/수정이 가능합니다.」
  → 인증 정보(`productCertificationInfos`)는 **지어 넣지 않는다**(받은 인증이 없으면 비운다).

규칙: KC 대상 카테고리면 상품의 `kc_exemption`(기본 "OVERSEAS" — 해외 구매대행)으로 특례 칸을 채운다. KC 대상이 아닌
카테고리는 손대지 않는다(템플릿 `{}` 그대로 — 통과 이력). 사전검증은 KC 대상인데 특례 칸이 비면 보류.
"""
from __future__ import annotations

import logging
import time
from typing import Dict, Optional

logger = logging.getLogger(__name__)

KEY = "naver_cat_detail:"
TTL_SEC = 7 * 24 * 3600
CODE = "naver_kc_exemption_unset"
EXEMPTION_TYPES = ("OVERSEAS", "SAFE_CRITERION", "PARALLEL_IMPORT")
_MEM: Dict[str, Dict] = {}


def _st():
    from src.db import image_translate_queue_pg as st
    return st


def detail(cid: str, uploader=None) -> Optional[Dict]:
    """카테고리 단건 조회 응답(7일 캐시). 못 받으면 None — 판정 못 함."""
    cid = str(cid or "").strip()
    if not cid:
        return None
    now = time.time()
    hit = _MEM.get(cid)
    if hit and now - float(hit.get("at") or 0) < TTL_SEC:
        return hit["data"]
    try:
        saved = _st().state_get(KEY + cid) or {}
    except Exception:                                            # noqa: BLE001
        saved = {}
    if saved.get("data") is not None and now - float(saved.get("at") or 0) < TTL_SEC:
        _MEM[cid] = saved
        return saved["data"]
    if uploader is None:
        return None
    try:
        res = uploader._api_request("GET", f"/v1/categories/{cid}")
    except Exception as exc:                                     # noqa: BLE001
        logger.warning("[네이버 KC] 카테고리 %s 조회 예외: %s", cid, exc)
        return None
    if not isinstance(res, dict) or "error" in res:
        logger.warning("[네이버 KC] 카테고리 %s 조회 실패: %s", cid, str((res or {}).get("error") if isinstance(res, dict) else res)[:200])
        return None
    rec = {"at": now, "data": {"exceptionalCategories": list(res.get("exceptionalCategories") or []),
                               "certificationInfos": [{"id": c.get("id"), "name": c.get("name"), "kindTypes": c.get("kindTypes")}
                                                      for c in res.get("certificationInfos") or [] if isinstance(c, dict)]}}
    _MEM[cid] = rec
    try:
        _st().state_set(KEY + cid, rec)
    except Exception:                                            # noqa: BLE001
        pass
    return rec["data"]


def kc_required(cid: str, uploader=None) -> Optional[bool]:
    d = detail(cid, uploader)
    if d is None:
        return None
    return "KC_CERTIFICATION" in (d.get("exceptionalCategories") or [])


def exemption_for(product: Dict) -> Dict:
    """상품의 KC 특례 — 기본 「해외구매대행」. `kc_exemption=""`로 끈 상품은 빈 칸(사전검증이 보류)."""
    t = str((product or {}).get("kc_exemption", "OVERSEAS") or "").strip().upper()
    if t not in EXEMPTION_TYPES:
        return {}
    return {"kcCertifiedProductExclusionYn": "KC_EXEMPTION_OBJECT", "kcExemptionType": t}


def _da(payload: Dict) -> Dict:
    return ((payload or {}).get("originProduct") or {}).get("detailAttribute") or {}


def apply(payload: Dict, product: Dict, uploader=None) -> Optional[bool]:
    """등록 몸통에 특례 칸을 채운다(KC 대상 카테고리만). 반환 = KC 대상 여부(None = 판정 못 함)."""
    cid = str(((payload or {}).get("originProduct") or {}).get("leafCategoryId") or "")
    req = kc_required(cid, uploader)
    if req:
        ex = exemption_for(product)
        if ex:
            _da(payload)["certificationTargetExcludeContent"] = ex
    return req


def hold(payload: Dict, required: Optional[bool]) -> Optional[Dict[str, str]]:
    """KC 대상인데 특례 칸이 비면 보류 `{code, line}`."""
    if not required:
        return None
    ct = _da(payload).get("certificationTargetExcludeContent") or {}
    if ct.get("kcCertifiedProductExclusionYn") == "KC_EXEMPTION_OBJECT" and ct.get("kcExemptionType") in EXEMPTION_TYPES:
        return None
    if str(ct.get("kcCertifiedProductExclusionYn") or "").upper() == "TRUE":
        return None
    return {"code": CODE,
            "line": "네이버 KC 인증 대상 카테고리예요 — KC 특례(해외구매대행) 칸이 비어 있어 보내지 않았어요. "
                    "받은 KC 인증 번호가 있으면 넣고, 없으면 해외구매대행 특례로 보내요"}

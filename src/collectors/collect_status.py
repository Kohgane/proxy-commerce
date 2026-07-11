"""src/collectors/collect_status.py — v47 STEP2: 수집 필드 상태(성공/부분) 단일 판정.

수집 1건이 어떤 필드를 실제로 담았는지 서버가 단일 소스로 판정한다(가짜 성공·무음 실패 금지).
- 성공: 핵심 필드(제목·가격·이미지) 완비 + 7개 필드 전부 present.
- 부분: 하나라도 누락 → 누락 필드명 나열('가격·이미지 누락' 식).
- 실패는 여기서 다루지 않는다(저장 자체가 안 되면 레코드가 없음 — 토스트/HTTP가 사유 표기).

확장/북마클릿 어느 경로로 수집돼도 저장된 extra dict만 보고 동일하게 판정 → 목록 상태 컬럼과
드로어 수집 로그가 같은 판정을 쓴다.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# 필드 순서 = 표시 순서. (키, 한글 라벨, 핵심 여부)
# v54 STEP3: 상태 배지를 **드로어 5탭 기준**으로 카운트(가격·갤러리·옵션·상세·리뷰). 제목은 거의 항상
#   있어 판정에서 제외(소스 로그용으로만 표시) → '7/7' 표기 오류 정리. '상세'=상세설명 또는 상세이미지 present.
FIELDS = [
    ("price", "가격", True),
    ("images", "갤러리", True),
    ("options", "옵션", False),
    ("detail", "상세", False),
    ("reviews", "리뷰·평점", False),
]
TOTAL = len(FIELDS)   # 5
_LABEL = {k: lbl for k, lbl, _ in FIELDS}
_CORE = {k for k, _, core in FIELDS if core}   # {price, images}


def _nonempty(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, (list, tuple, dict)):
        return len(v) > 0
    return bool(str(v).strip())


def _field_present(key: str, extra: Dict[str, Any], title_fallback: str = "") -> bool:
    """extra dict에서 해당 필드가 실제로 채워졌는지(정직 present) 판정."""
    if key == "title":
        return _nonempty(extra.get("title_ko") or extra.get("title") or title_fallback)
    if key == "price":
        # 가격은 값이 있고 + '확인 필요'(needs_check)가 아닐 때만 present(임의 확정 금지).
        return _nonempty(extra.get("price")) and str(extra.get("price_status") or "") != "needs_check"
    if key == "images":
        return _nonempty(extra.get("images")) or _nonempty(extra.get("gallery_images"))
    if key == "options":
        return _nonempty(extra.get("options"))
    if key == "detail":
        # v54: '상세' = 상세설명(≥20자) 또는 상세이미지 배열(테무 상세 본체) present.
        d = extra.get("description_ko") or extra.get("description") or ""
        return len(str(d).strip()) >= 20 or _nonempty(extra.get("detail_images"))
    if key == "description":   # 하위호환(개별 조회용)
        d = extra.get("description_ko") or extra.get("description") or ""
        return len(str(d).strip()) >= 20
    if key == "detail_images":
        return _nonempty(extra.get("detail_images"))
    if key == "reviews":
        return (_nonempty(extra.get("reviews"))
                or _nonempty(extra.get("rating"))
                or _nonempty(extra.get("review_count")))
    return False


def compute_collect_status(
    extra: Optional[Dict[str, Any]],
    title_fallback: str = "",
    sources: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """수집 필드 상태를 단일 판정한다.

    Args:
        extra: 저장된 수집 상세 dict(images/price/options/…).
        title_fallback: extra에 제목이 없을 때 행 title로 폴백.
        sources: (선택) 필드키→추출소스("json"/"dom"/"server"). 있으면 로그에 소스 표기.

    Returns:
        {status: '성공'|'부분', filled: N, total: 7, present: [...], missing: [...라벨],
         core_missing: [...라벨], fields: [{key,label,ok,core,source}]}
    """
    extra = extra if isinstance(extra, dict) else {}
    sources = sources if isinstance(sources, dict) else {}
    present_labels: List[str] = []
    missing_labels: List[str] = []
    core_missing: List[str] = []
    fields: List[Dict[str, Any]] = []
    filled = 0
    for key, label, core in FIELDS:
        ok = _field_present(key, extra, title_fallback)
        src = str(sources.get(key) or "").strip().lower()
        # 소스가 안 넘어오면 present는 '있음', 누락은 '없음'(가짜 소스 날조 금지).
        # v51: Tier 라벨(Tier1=캡처 API/초기상태·Tier2=렌더 DOM·Tier3=og/meta) + 하위호환(json/dom/server).
        src_label = {
            "tier1": "Tier1(API/상태)", "tier2": "Tier2(DOM)", "tier3": "Tier3(og)",
            "ldjson": "ld+json", "json": "JSON", "dom": "DOM", "server": "서버파싱",
        }.get(src, ("있음" if ok else "없음"))
        fields.append({"key": key, "label": label, "ok": ok, "core": core, "source": src_label})
        if ok:
            filled += 1
            present_labels.append(label)
        else:
            missing_labels.append(label)
            if core:
                core_missing.append(label)
    # v54 STEP3: 제목은 카운트 제외(거의 항상 있음) — 소스 로그용으로만 fields 앞에 표시.
    _t_ok = _field_present("title", extra, title_fallback)
    _t_src = str(sources.get("title") or "").strip().lower()
    _t_label = {
        "tier1": "Tier1(API/상태)", "tier2": "Tier2(DOM)", "tier3": "Tier3(og)",
        "ldjson": "ld+json", "json": "JSON", "dom": "DOM", "server": "서버파싱",
    }.get(_t_src, ("있음" if _t_ok else "없음"))
    fields.insert(0, {"key": "title", "label": "제목", "ok": _t_ok, "core": False, "source": _t_label, "count": False})
    # v49 STEP5: 3단계 — 성공(전 필드)/부분(일부 누락)/실패(핵심 3 전부 미확보=추출 실패).
    #   저장은 됐으나 제목·가격·이미지가 모두 없으면 '부분'이 아니라 '실패'로 정직 표기(원인 명시).
    _core_total = len(_CORE)
    if filled == TOTAL:
        status = "성공"
        cause = ""
    elif len(core_missing) >= _core_total:
        status = "실패"
        cause = "추출 실패 — 핵심 정보(가격·갤러리)를 못 읽었어요"
    else:
        status = "부분"
        cause = ""
    # 뱃지·토스트용 간결 누락 목록: 핵심 누락이 있으면 핵심만(가장 급함), 없으면 부가 누락 최대 3개.
    missing_short = core_missing if core_missing else missing_labels[:3]
    return {
        "status": status,
        "cause": cause,
        "filled": filled,
        "total": TOTAL,
        "present": present_labels,
        "missing": missing_labels,
        "missing_short": missing_short,
        "core_missing": core_missing,
        "fields": fields,
    }


def status_summary(st: Dict[str, Any]) -> str:
    """토스트/뱃지용 한 줄 요약. 성공(7/7)/부분(누락)/실패(원인)."""
    if not st:
        return ""
    if st.get("status") == "성공":
        return f"수집 완료({st.get('filled')}/{st.get('total')} 필드)"
    if st.get("status") == "실패":
        return f"수집 실패 — {st.get('cause') or '핵심 정보 미확보'}"
    miss = "·".join(st.get("missing_short") or st.get("missing") or [])
    return f"부분 수집 — {miss} 누락" if miss else "부분 수집"

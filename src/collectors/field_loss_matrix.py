"""src/collectors/field_loss_matrix.py — v63 STEP2: 필드 손실 지도 + 품질 게이트.

수집된 상품(collect_history)의 저장 extra를 도메인(테무·아마존·요시다·기타)별로 집계해
[필드 × 채택 tier × 결과] 매트릭스와 도메인별 충족률을 산출한다. **추측 서술 금지** — 실제
저장된 collect_status(compute_collect_status가 수집 시 기록)만 읽어 집계한다.

품질 게이트: 디폴트 마켓 상품 상세의 [제목·가격·이미지≥3·옵션(존재 시)·상세] 충족률이 90% 미만이면
해당 어댑터를 'incomplete'(미완)로 표기 → diagnostics가 '완료' 서술을 못 하게 한다.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .collect_status import _field_present

# 디폴트 마켓(어댑터) 도메인 정규화 — 품질 게이트 대상.
_DOMAIN_PATTERNS = [
    ("amazon", re.compile(r"(^|\.)amazon\.[a-z.]+", re.I)),
    ("temu", re.compile(r"(^|\.)temu\.com", re.I)),
    ("aliexpress", re.compile(r"(^|\.)aliexpress\.[a-z.]+", re.I)),
    ("taobao", re.compile(r"(^|\.)taobao\.com", re.I)),
    ("tmall", re.compile(r"(^|\.)tmall\.com", re.I)),
    ("1688", re.compile(r"(^|\.)1688\.com", re.I)),
    ("yahoo", re.compile(r"(^|\.)(shopping\.)?yahoo\.co\.jp|paypaymall\.yahoo\.co\.jp", re.I)),
    ("yoshida", re.compile(r"(^|\.)yoshidakaban\.com", re.I)),
]
# 어댑터(디폴트 마켓) 게이트 대상 도메인 — 요시다는 제네릭 대조군이라 게이트 정보용.
DEFAULT_MARKET_DOMAINS = {"amazon", "temu", "aliexpress", "taobao", "tmall", "1688", "yahoo"}

# 품질 게이트 필드(브리프 명세): 제목·가격·이미지≥3·옵션(존재 시)·상세.
GATE_FIELDS = ["title", "price", "images3", "options", "detail"]
COMPLETE_THRESHOLD = 0.90


def domain_of(url: str) -> str:
    """URL → 정규화 도메인 키(매트릭스 그룹). 매칭 없으면 호스트 그대로(기타)."""
    u = str(url or "")
    host = ""
    m = re.match(r"https?://([^/]+)", u, re.I)
    if m:
        host = m.group(1).lower()
    for name, pat in _DOMAIN_PATTERNS:
        if pat.search(host):
            return name
    return host or "unknown"


def _images_count(extra: Dict[str, Any]) -> int:
    imgs = extra.get("images") or extra.get("gallery_images") or []
    return len(imgs) if isinstance(imgs, (list, tuple)) else 0


def _gate_present(field: str, extra: Dict[str, Any], title_fallback: str = "") -> bool:
    """품질 게이트 필드 present 판정(이미지는 ≥3, 나머지는 collect_status 규약 재사용)."""
    if field == "images3":
        return _images_count(extra) >= 3
    return _field_present(field, extra, title_fallback)


def item_completeness(extra: Optional[Dict[str, Any]], title_fallback: str = "") -> Dict[str, Any]:
    """상품 1건의 게이트 충족(분자/분모). 옵션은 '존재 시'만 분모에 포함(무옵션 상품 미감점)."""
    extra = extra if isinstance(extra, dict) else {}
    per: Dict[str, bool] = {}
    for f in GATE_FIELDS:
        per[f] = _gate_present(f, extra, title_fallback)
    # 옵션은 present일 때만 분모에 포함(존재 시). 나머지 4개는 항상 분모.
    applicable = [f for f in GATE_FIELDS if f != "options"]
    if per["options"]:
        applicable.append("options")
    filled = sum(1 for f in applicable if per[f])
    denom = len(applicable)
    return {"per_field": per, "filled": filled, "applicable": denom,
            "ratio": (filled / denom) if denom else 0.0}


def _iter_extra(items: List[Dict[str, Any]]):
    """history 행에서 (url, extra dict, title) 추출 — extra/extra_json 양쪽 수용."""
    for it in items or []:
        if not isinstance(it, dict):
            continue
        extra = it.get("extra") if isinstance(it.get("extra"), dict) else it.get("extra_json")
        extra = extra if isinstance(extra, dict) else {}
        url = it.get("url") or it.get("source_url") or extra.get("url") or ""
        title = it.get("title") or extra.get("title_ko") or extra.get("title") or ""
        yield url, extra, title


def build_field_loss_matrix(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """도메인별 [필드×tier×결과] 매트릭스 + 충족률. 저장된 collect_status만 집계(추측 0)."""
    domains: Dict[str, Any] = {}
    for url, extra, title in _iter_extra(items):
        dom = domain_of(url)
        d = domains.setdefault(dom, {
            "domain": dom, "count": 0,
            "field_present": {}, "field_source": {},  # field→present건수 / field→{tier:건수}
            "completeness_sum": 0.0, "gate_field_hits": {f: 0 for f in GATE_FIELDS},
        })
        d["count"] += 1
        # 필드×tier: 저장된 collect_status.fields(있으면) 우선, 없으면 present만.
        st = extra.get("collect_status") if isinstance(extra.get("collect_status"), dict) else None
        fields = st.get("fields") if st and isinstance(st.get("fields"), list) else None
        if fields:
            for fl in fields:
                k = fl.get("key"); ok = bool(fl.get("ok")); src = str(fl.get("source") or "").strip()
                if not k:
                    continue
                if ok:
                    d["field_present"][k] = d["field_present"].get(k, 0) + 1
                    d["field_source"].setdefault(k, {})
                    d["field_source"][k][src] = d["field_source"][k].get(src, 0) + 1
        # 품질 게이트 충족.
        comp = item_completeness(extra, title)
        d["completeness_sum"] += comp["ratio"]
        for f in GATE_FIELDS:
            if comp["per_field"][f]:
                d["gate_field_hits"][f] += 1
    # 도메인별 요약.
    out_domains = []
    for dom, d in domains.items():
        n = d["count"] or 1
        completeness = d["completeness_sum"] / n
        is_market = dom in DEFAULT_MARKET_DOMAINS
        complete = completeness >= COMPLETE_THRESHOLD
        out_domains.append({
            "domain": dom, "count": d["count"],
            "completeness": round(completeness, 4),
            "complete": complete,
            "status": ("완료" if complete else "미완") if is_market else "대조군",
            "is_default_market": is_market,
            "field_present": d["field_present"],
            "field_source": d["field_source"],
            "gate_field_rate": {f: round(d["gate_field_hits"][f] / n, 4) for f in GATE_FIELDS},
        })
    out_domains.sort(key=lambda x: (not x["is_default_market"], x["completeness"]))
    return {"domains": out_domains, "total_items": sum(x["count"] for x in out_domains)}


def adapter_quality_gate(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """디폴트 마켓 어댑터별 품질 게이트 결과(diagnostics 표기용). 90% 미만=미완."""
    matrix = build_field_loss_matrix(items)
    gate = []
    for d in matrix["domains"]:
        if not d["is_default_market"]:
            continue
        gate.append({
            "adapter": d["domain"], "count": d["count"],
            "completeness": d["completeness"], "complete": d["complete"],
            "status": d["status"],  # '완료'/'미완'
            "threshold": COMPLETE_THRESHOLD,
            "weak_fields": [f for f, r in d["gate_field_rate"].items() if r < COMPLETE_THRESHOLD],
        })
    return gate

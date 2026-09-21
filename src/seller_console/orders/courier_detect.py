"""src/seller_console/orders/courier_detect.py — F44-p **택배사 판별 프로브**.

## 무엇을 정하려고 재나 (오너 2026-09-21)

> 택배사 자동판별 공급사는 **하나만**. 먼저 `TrackingMore.detect_courier`가
> 한국 5대(CJ·롯데·한진·우체국·로젠) + 국제(EMS·DHL·FedEx·UPS)를 판별하는지 실측.
> 되면 TrackingMore 유지, **17TRACK 안 붙인다.** 안 되면 17TRACK으로 **통째 교체**(둘 병존 금지).

## ★★ 키를 옮기지 말고 **측정을 옮긴다** (오너 규칙, 2026-09-21)

예전 판이면 스크립트를 주고 「키 넣고 돌려 보세요」 했다. 그러면 **키가 돌아다닌다.**
이 모듈은 **서버 env(`TRACKINGMORE_API_KEY`)를 그대로 읽는 라우트**의 속이고,
오너는 관리자 화면에서 **송장번호만 붙여 넣는다.** 키는 있던 자리에 있는다.

## 판정 셋 — 부분 통과를 통과로 읽지 않는다

| 값 | 뜻 |
|---|---|
| `판별` | 공급사가 그 택배사를 **1순위로** 지목했다 |
| `후보` | 후보 안에는 있지만 1순위가 아니다 |
| `못함` | 후보에 없다 · 빈 목록 · 호출 실패 |

**`못함`이 하나라도 있으면 TrackingMore 단독으로는 부족한 것**이다.
"""
from __future__ import annotations

import logging
from typing import Dict, List

logger = logging.getLogger(__name__)

#: 오너가 지목한 9곳. 이름은 우리 카탈로그(`courier_catalog`) 표기와 맞춘다.
TARGETS = (
    ("CJ대한통운", "국내"), ("롯데택배", "국내"), ("한진택배", "국내"),
    ("우체국택배", "국내"), ("로젠택배", "국내"),
    ("EMS", "국제"), ("DHL", "국제"), ("FedEx", "국제"), ("UPS", "국제"),
)

VERDICT_HIT, VERDICT_CAND, VERDICT_MISS = "판별", "후보", "못함"


def parse_input(text: str) -> List[Dict]:
    """붙여 넣은 여러 줄 → `[{name, number}]`.

    한 줄에 `택배사<탭 또는 공백>송장번호`. 이름 없이 번호만 넣어도 된다 —
    그 경우 **기대값 없이** 무엇으로 판별되는지만 본다(그것도 답이다).
    """
    rows = []
    for line in str(text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t") if "\t" in line else line.split(None, 1)
        if len(parts) == 2:
            rows.append({"name": parts[0].strip(), "number": parts[1].strip()})
        else:
            rows.append({"name": "", "number": parts[0].strip()})
    return rows


def _catalog_index() -> Dict[str, Dict]:
    from .courier_catalog import get_courier_catalog
    idx = {}
    for row in get_courier_catalog(include_dynamic=True):
        for term in row.get("search_terms", []):
            idx.setdefault(str(term).lower(), row)
    return idx


def probe(text: str) -> Dict:
    """붙여 넣은 목록을 판별해 **표와 결론**을 낸다.

    결론은 셋 중 하나다: `keep`(TrackingMore 유지) · `replace`(17TRACK 교체 검토) ·
    `unknown`(잰 게 없어 못 정함). **못 잰 것을 통과로 읽지 않는다.**
    """
    from .tracking_trackingmore import TrackingMoreClient

    client = TrackingMoreClient()
    if not client.active:
        return {"ok": False, "rows": [], "verdict": "unknown",
                "error": "TRACKINGMORE_API_KEY가 이 서버에 없습니다 — 판별을 잴 수 없습니다.",
                "targets": [n for n, _k in TARGETS]}

    idx = _catalog_index()
    rows, misses, measured = [], [], 0
    for item in parse_input(text):
        name, number = item["name"], item["number"]
        known = idx.get(name.lower()) if name else None
        want = (known or {}).get("trackingmore_code", "")
        got = client.detect_detail(number)
        codes = got.get("codes") or []

        if not codes:
            verdict, note = VERDICT_MISS, got.get("error") or "후보가 없습니다"
        elif not want:
            # 기대값이 없으면 **맞다/틀리다를 말하지 않는다** — 무엇이 나왔는지만 적는다.
            verdict, note = "참고", f"1순위={codes[0]}"
        elif codes[0] == want:
            verdict, note = VERDICT_HIT, f"1순위={codes[0]}"
        elif want in codes:
            verdict, note = VERDICT_CAND, f"1순위={codes[0]} · 우리 코드는 {want}"
        else:
            verdict, note = VERDICT_MISS, f"후보={codes[:3]} · 우리 코드는 {want}"

        if want:
            measured += 1
            if verdict == VERDICT_MISS:
                misses.append(name)
        rows.append({
            "name": name, "number": number,
            "in_catalog": bool(known), "our_code": want,
            "codes": codes, "verdict": verdict, "note": note,
            "raw": got.get("raw", ""), "http_status": got.get("http_status"),
            "error": got.get("error", ""),
        })

    covered = {r["name"] for r in rows if r["name"] and r["verdict"] in (VERDICT_HIT, VERDICT_CAND)}
    untested = [n for n, _k in TARGETS if n not in {r["name"] for r in rows}]
    if not measured:
        verdict = "unknown"
    elif misses or untested:
        verdict = "replace"
    else:
        verdict = "keep"
    return {
        "ok": True, "rows": rows, "verdict": verdict,
        "misses": sorted(set(misses)), "untested": untested,
        "covered": sorted(covered), "measured": measured,
        "targets": [n for n, _k in TARGETS],
        "error": "",
    }


def verdict_sentence(result: Dict) -> str:
    """사람이 읽을 결론 한 줄. **부분 통과를 통과로 읽지 않는다.**"""
    v = (result or {}).get("verdict")
    if v == "keep":
        return "9곳 전부 다룹니다 → TrackingMore 유지, 17TRACK 안 붙입니다."
    if v == "replace":
        gaps = (result.get("misses") or []) + (result.get("untested") or [])
        return ("아직 다 못 잽니다 — " + ", ".join(gaps[:9]) +
                " (안 잰 곳이 있으면 그것도 「통과」가 아닙니다). "
                "전부 채운 뒤에도 못 다루는 곳이 남으면 17TRACK 교체를 검토합니다.")
    return result.get("error") or "잰 것이 없습니다 — 송장번호를 넣어 주세요."

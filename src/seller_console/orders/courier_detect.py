"""src/seller_console/orders/courier_detect.py — 택배사 **판별 프로브** (F44-p → F44-b).

## 무엇을 정하려고 재나

F44-p에서 TrackingMore로 재려 했다. 그 사이 오너 실측으로 **무료 쿼터가 소진**됐고
(`code 4190`), 오너가 공급사를 **17TRACK으로 교체**하기로 정했다(**병존 금지**).
이 화면은 그대로 두고 **속만 갈아 끼운다** — 재는 자리를 옮기지 않는다.

## ★★ 키를 옮기지 말고 **측정을 옮긴다** (오너 규칙, 2026-09-21)

예전 판이면 스크립트를 주고 「키 넣고 돌려 보세요」 했다. 그러면 **키가 돌아다닌다.**
이 모듈은 **서버 env(`SEVENTEENTRACK_API_KEY`)를 그대로 읽는 라우트**의 속이고,
오너는 관리자 화면에서 **송장번호만 붙여 넣는다.** 키는 있던 자리에 있는다.

## ★ 이 측정은 **쿼터를 쓴다**

TrackingMore엔 공짜 판별(`couriers/detect`)이 있었지만 17TRACK엔 없다 —
**판별은 등록의 부산물**이다. 그래서 한 줄 = 쿼터 한 칸이고,
프로브는 **전후 잔량을 같이 재서** 몇 칸을 썼는지 화면에 적는다. 모르고 태우지 않도록.

## 판정 셋 — 부분 통과를 통과로 읽지 않는다

| 값 | 뜻 |
|---|---|
| `판별` | 공급사가 **`accepted`**에 넣고 캐리어 코드를 줬다 |
| `참고` | 판별은 됐지만 **우리 코드표가 없어** 맞다/틀리다를 말할 수 없다 |
| `못함` | 거절됐다 · 빈 목록 · 호출 실패 |

**`accepted` 배열이 증거다** — 200은 등록의 증거가 아니다
(볼트 [[17TRACK 등록 조용한 실패]]). `못함`이 하나라도 있으면 그 택배사는 **아직 못 다룬다.**
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

VERDICT_HIT, VERDICT_CAND, VERDICT_MISS, VERDICT_INFO = "판별", "후보", "못함", "참고"

#: 우리 카탈로그의 17TRACK 코드 축. 캐리어 목록 문서가 오기 전까진 **전부 빈칸**이고,
#: 그때는 「맞다/틀리다」 대신 **되돌아온 코드만** 적는다(F44-a와 같은 규율).
OUR_CODE_FIELD = "seventeentrack_code"


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

    결론 셋: `ready`(9곳 다룬다) · `gap`(못 다루는 곳이 있다) · `unknown`(잰 게 없다).
    **못 잰 것을 통과로 읽지 않는다.**
    """
    from .tracking_17track import API_KEY_ENV, SeventeenTrackClient

    client = SeventeenTrackClient()
    if not client.active:
        return {"ok": False, "rows": [], "verdict": "unknown",
                "error": f"{API_KEY_ENV}가 이 서버에 없습니다 — 판별을 잴 수 없습니다.",
                "targets": [n for n, _k in TARGETS], "quota": {}, "spent": None}

    # ★ 전후 잔량 — 이 측정이 **몇 칸을 썼는지** 화면이 말할 수 있어야 한다.
    before = client.quota()

    idx = _catalog_index()
    rows, misses, measured = [], [], 0
    for item in parse_input(text):
        name, number = item["name"], item["number"]
        known = idx.get(name.lower()) if name else None
        want = str((known or {}).get(OUR_CODE_FIELD) or "")
        got = client.detect_detail(number)
        codes = [str(c) for c in (got.get("codes") or [])]

        if not codes:
            verdict, note = VERDICT_MISS, got.get("error") or "후보가 없습니다"
        elif not want:
            # 기대값이 없으면 **맞다/틀리다를 말하지 않는다** — 무엇이 나왔는지만 적는다.
            verdict = VERDICT_INFO
            note = f"판별 코드={codes[0]} · 우리 코드표 없음(17TRACK 캐리어 목록 대기)"
        elif codes[0] == want:
            verdict, note = VERDICT_HIT, f"1순위={codes[0]}"
        elif want in codes:
            verdict, note = VERDICT_CAND, f"1순위={codes[0]} · 우리 코드는 {want}"
        else:
            verdict, note = VERDICT_MISS, f"후보={codes[:3]} · 우리 코드는 {want}"

        if name:
            measured += 1
            if verdict == VERDICT_MISS:
                misses.append(name)
        rows.append({
            "name": name, "number": number,
            "in_catalog": bool(known), "our_code": want,
            "codes": codes, "verdict": verdict, "note": note,
            "accepted": bool(got.get("accepted")),
            "raw": got.get("raw", ""), "http_status": got.get("http_status"),
            "error": got.get("error", ""),
        })

    after = client.quota()
    untested = [n for n, _k in TARGETS if n not in {r["name"] for r in rows}]
    # ★★★ 「판별됐다」와 「맞는 걸 판별했다」는 **다른 사실**이다.
    #   우리 코드표가 없으면 공급사가 무언가를 내놨다는 것만 알 뿐, 그게 그 택배사인지는
    #   확인 못 한다. 그걸 `ready`로 묶으면 **부분 통과를 통과로 읽는 것**이다.
    unverified = sorted({r["name"] for r in rows
                         if r["name"] and r["verdict"] == VERDICT_INFO})
    if not measured:
        verdict = "unknown"
    elif misses or untested:
        verdict = "gap"
    elif unverified:
        verdict = "unverified"
    else:
        verdict = "ready"
    return {
        "ok": True, "rows": rows, "verdict": verdict,
        "misses": sorted(set(misses)), "untested": untested,
        # ※ 예전엔 `covered`(다룬 곳)도 실어 보냈는데 **아무도 안 읽었고**,
        #   `참고`를 `판별`과 한 덩어리로 세고 있었다 — 위 ★★★가 고친 그 혼동이다.
        #   안 읽히는 값이 틀린 뜻을 들고 있으면 다음 사람이 그대로 화면에 붙인다. 지웠다.
        "unverified": unverified, "measured": measured,
        "targets": [n for n, _k in TARGETS],
        "quota": after if after.get("ok") else before,
        "spent": _spent(before, after),
        "error": "",
    }


def _spent(before: Dict, after: Dict):
    """이 측정이 **몇 칸을 썼나**. 한쪽이라도 못 읽었으면 `None`(모른다고 말한다)."""
    b, a = (before or {}).get("remain"), (after or {}).get("remain")
    if not isinstance(b, int) or not isinstance(a, int):
        return None
    return b - a


def quota_sentence(quota: Dict, spent=None) -> str:
    """잔량 한 줄. **못 읽었으면 그렇게 말한다** — 숫자를 지어내지 않는다."""
    q = quota or {}
    if not q:
        return "남은 쿼터를 읽지 않았습니다."
    if not q.get("ok"):
        return "남은 쿼터를 읽지 못했습니다 — " + (q.get("error") or "사유 불명")
    parts = [f"남은 쿼터 {q.get('remain')} / 전체 {q.get('total')}"]
    if isinstance(q.get("today_used"), int):
        parts.append(f"오늘 {q['today_used']}칸")
    if q.get("max_daily") == 0:
        parts.append("일 한도 없음")
    elif isinstance(q.get("max_daily"), int):
        parts.append(f"일 한도 {q['max_daily']}")
    if isinstance(spent, int):
        parts.append(f"이번 측정 {spent}칸")
    return " · ".join(parts)


def verdict_sentence(result: Dict) -> str:
    """사람이 읽을 결론 한 줄. **부분 통과를 통과로 읽지 않는다.**"""
    v = (result or {}).get("verdict")
    if v == "ready":
        return "넣은 곳은 전부 판별됐고 우리 코드와도 맞았습니다."
    if v == "unverified":
        # ★ 여기서 「전부 판별됐습니다」로 끝내면 **확인 못 한 것을 확인했다고** 말하는 것이다.
        names = ", ".join((result.get("unverified") or [])[:9])
        return ("전부 판별은 됐지만 **맞는지는 확인 못 했습니다** — "
                f"우리 코드표가 비어 있습니다({names}). "
                "17TRACK 캐리어 목록 URL을 넣으면 그때 대조합니다.")
    if v == "gap":
        gaps = (result.get("misses") or []) + (result.get("untested") or [])
        return ("아직 다 못 잽니다 — " + ", ".join(gaps[:9]) +
                " (안 잰 곳이 있으면 그것도 「통과」가 아닙니다).")
    return result.get("error") or "잰 것이 없습니다 — 송장번호를 넣어 주세요."

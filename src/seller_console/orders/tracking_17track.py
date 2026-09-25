"""src/seller_console/orders/tracking_17track.py — F44-b **17TRACK 추적 공급사**.

## 왜 갈아탔나 (오너 결정 2026-09-21)

> TrackingMore 무료 쿼터 **소진**(`code 4190`, 실측) → 17TRACK으로 **교체**. **병존 금지.**

두 공급사를 나란히 두면 「어느 쪽이 답했나」가 화면마다 갈리고, 죽은 쪽이 남아
**쓰지도 않는 키를 계속 물어보게** 된다. 그래서 TrackingMore는 이 PR에서 **지운다.**

## 문서에서 확인한 것만 쓴다 (발명 0)

| 무엇 | 값 |
|---|---|
| 기준 URL | `https://api.17track.net/track/v2.4` |
| 인증 헤더 | `17token` (+ `Content-Type: application/json`) |
| 등록 | `POST /register` · 본문 `[{"number": …, "carrier": <int 선택>}]` (한 번에 40개) |
| 등록 응답 | `{code, data:{accepted:[{origin,number,carrier}], rejected:[{number,error:{code,message}}]}}` |
| 쿼터 | `POST /getquota` · 본문 `[]` → `{quota_total, quota_used, quota_remain, today_used, max_track_daily}` |
| 캐리어 미감지 | 오류 코드 **`-18019903`** = `Carrier cannot be detected.` |

**캐리어 코드는 17TRACK 목록의 `key` 필드**(정수)다. 그 목록 URL은 문서에 링크로만 있고
여기 받아 적힌 값이 없어 **짐작해 박지 않는다** — `SEVENTEENTRACK_CARRIER_LIST_URL`이
설정되면 이름을 붙이고, 없으면 **코드만** 보여 주고 그렇다고 말한다.

## ★★ `accepted` 배열이 증거다 (볼트 지뢰 [[17TRACK 등록 조용한 실패]])

다른 프로젝트에서 이미 밟았다: `add()`가 **register 실패를 무시하고 DB에만 기록**해
송장이 「조회 불가」로 방치됐다. **응답이 200인 것은 등록된 것이 아니다** —
`accepted`에 들어갔는지를 본다. 그리고 `accepted`조차 **등록 성공이지 추적 성공은 아니다.**

## ★ 이 호출은 **쿼터를 쓴다**

TrackingMore의 `couriers/detect`는 공짜 조회였다. 17TRACK엔 그런 자리가 없고,
**판별은 등록의 부산물**이다(`accepted[].carrier`). 그래서 판별 한 번 = 쿼터 한 칸이다.
화면이 그 사실과 **전후 잔량**을 같이 적는다 — 모르고 태우지 않도록.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

import requests

from src.utils.env import env_str

logger = logging.getLogger(__name__)

BASE = "https://api.17track.net/track/v2.4"
API_KEY_ENV = "SEVENTEENTRACK_API_KEY"
CARRIER_LIST_URL_ENV = "SEVENTEENTRACK_CARRIER_LIST_URL"

#: 「캐리어를 못 찾았다」 — 문서에 적힌 그대로의 오류 코드.
ERR_CARRIER_NOT_DETECTED = -18019903

#: 한 번에 보낼 수 있는 송장 수(문서 값). 넘기면 공급사가 자른다.
MAX_BATCH = 40

_TIMEOUT = 10


class SeventeenTrackClient:
    """17TRACK Track API v2.4 클라이언트.

    키가 없으면 **부르지 않고 사유를 돌려준다** — 빈 결과로 「못 찾았다」인 척하지 않는다.
    """

    def __init__(self) -> None:
        self.api_key = env_str(API_KEY_ENV)
        self.active = bool(self.api_key)

    # ── 공통 ────────────────────────────────────────────────────────────
    def _headers(self) -> dict:
        return {"17token": self.api_key or "", "Content-Type": "application/json"}

    def _mask(self, text: str) -> str:
        from src.utils.secret_mask import mask_text
        return mask_text(str(text or ""), secrets=(self.api_key or "",))

    def _post(self, path: str, payload) -> Dict:
        """`{ok, code, data, raw, http_status, error}` — **원문까지 들고 나온다**(F41 규율).

        빈 결과가 「못 찾음」인지 「쿼터 소진」인지 「키 오류」인지는 **원문에만** 있다.
        """
        out = {"ok": False, "code": None, "data": None, "raw": "",
               "http_status": None, "error": ""}
        if not self.active:
            out["error"] = f"{API_KEY_ENV}가 이 서버에 설정되지 않았습니다"
            return out
        try:
            r = requests.post(f"{BASE}{path}", json=payload,
                              headers=self._headers(), timeout=_TIMEOUT)
        except Exception as exc:
            logger.warning("[17TRACK] %s 호출 실패: %s", path, exc)
            out["error"] = f"호출 오류: {type(exc).__name__}"
            return out

        body = self._mask(getattr(r, "text", "") or "")
        out["http_status"] = r.status_code
        out["raw"] = body[:300] or "본문을 주지 않았습니다(빈 응답)"
        if r.status_code >= 400:
            logger.warning("[17TRACK] %s HTTP %s: %s", path, r.status_code, body[:2000])
            out["error"] = f"공급사가 거부했습니다 (HTTP {r.status_code})"
            return out
        try:
            js = r.json()
        except Exception as exc:
            out["error"] = f"응답을 해석하지 못했습니다: {type(exc).__name__}"
            return out

        out["code"] = js.get("code")
        out["data"] = js.get("data")
        if out["code"] not in (0, None):
            # 공급사가 200으로 실패를 말하는 자리 — 여기를 안 보면 조용한 실패가 된다.
            out["error"] = f"공급사 오류 코드 {out['code']}"
            return out
        out["ok"] = True
        return out

    # ── 쿼터 ────────────────────────────────────────────────────────────
    def quota(self) -> Dict:
        """남은 쿼터 — `{ok, total, used, remain, today_used, max_daily, error, raw}`.

        오너 지시: **「17TRACK도 무료 한도가 있으니 남은 쿼터를 화면에 적어라.」**
        TrackingMore는 한도를 다 쓴 뒤에야 `4190`으로 알려 줬다 — 그건 늦다.
        """
        got = self._post("/getquota", [])
        d = got.get("data") or {}
        return {
            "ok": bool(got["ok"]) and isinstance(d, dict),
            "total": d.get("quota_total"),
            "used": d.get("quota_used"),
            "remain": d.get("quota_remain"),
            "today_used": d.get("today_used"),
            # 문서: 0이면 **무제한**이다. 0을 「오늘 한 건도 못 쓴다」로 읽으면 정반대가 된다.
            "max_daily": d.get("max_track_daily"),
            "raw": got.get("raw", ""),
            "http_status": got.get("http_status"),
            "error": got.get("error", ""),
        }

    # ── 등록 = 판별 ─────────────────────────────────────────────────────
    def register(self, numbers: List[Dict]) -> Dict:
        """송장 등록 — `{ok, accepted, rejected, raw, http_status, error}`.

        `numbers` = `[{"number": …, "carrier": <int 선택>}]`.

        ★★ **`accepted` 배열이 증거다.** 200을 받았다고 등록된 것이 아니다
        (볼트 [[17TRACK 등록 조용한 실패]] — 그렇게 송장 하나가 조회 불가로 방치됐다).
        """
        rows = [r for r in (numbers or []) if str(r.get("number") or "").strip()]
        if not rows:
            return {"ok": False, "accepted": [], "rejected": [], "raw": "",
                    "http_status": None, "error": "등록할 송장번호가 없습니다"}
        if len(rows) > MAX_BATCH:
            return {"ok": False, "accepted": [], "rejected": [], "raw": "",
                    "http_status": None,
                    "error": f"한 번에 {MAX_BATCH}개까지입니다(받은 것 {len(rows)}개)"}

        got = self._post("/register", rows)
        d = got.get("data") or {}
        accepted = list(d.get("accepted") or []) if isinstance(d, dict) else []
        rejected = list(d.get("rejected") or []) if isinstance(d, dict) else []
        err = got.get("error", "")
        if got["ok"] and not accepted and not rejected:
            # 200 + 빈 양쪽 = 무슨 일이 있었는지 아무도 말하지 않았다. 성공이 아니다.
            err = "공급사가 accepted도 rejected도 주지 않았습니다"
        return {"ok": bool(got["ok"]) and bool(accepted), "accepted": accepted,
                "rejected": rejected, "raw": got.get("raw", ""),
                "http_status": got.get("http_status"), "error": err}

    def detect_detail(self, tracking_no: str, carrier: Optional[int] = None) -> Dict:
        """택배사 자동판별 — `{codes, accepted, raw, http_status, error}`.

        ★ 17TRACK엔 **공짜 판별 자리가 없다.** 판별은 등록의 부산물이므로
        이 호출은 **쿼터를 한 칸 쓴다.** 화면이 그렇게 적는다.

        `codes`는 17TRACK **캐리어 코드(정수)** 목록이다 — 우리 코드가 아니다.
        """
        row: Dict = {"number": str(tracking_no or "").strip()}
        if carrier:
            row["carrier"] = int(carrier)
        got = self.register([row])

        codes = [a.get("carrier") for a in got["accepted"] if a.get("carrier")]
        err = got.get("error", "")
        if not codes and got["rejected"]:
            e = (got["rejected"][0] or {}).get("error") or {}
            code, msg = e.get("code"), str(e.get("message") or "").strip()
            if code == ERR_CARRIER_NOT_DETECTED:
                err = "캐리어를 자동으로 찾지 못했습니다 — 코드를 지정해야 등록됩니다"
            else:
                err = f"공급사가 거절했습니다({code}): {msg}" if code else (msg or err)
        elif not codes and not err:
            err = "후보가 없습니다(공급사가 빈 목록을 냈다)"
        return {"codes": codes, "accepted": bool(got["accepted"]), "raw": got.get("raw", ""),
                "http_status": got.get("http_status"), "error": err}

    # ── 상태 ────────────────────────────────────────────────────────────
    def health_check(self) -> Dict:
        """키가 살아 있나 — **쿼터 조회로 확인한다**(등록과 달리 칸을 안 쓴다).

        `{status: ok|missing|fail, remain, total, ...}`.
        """
        if not self.active:
            return {"status": "missing", "hint": f"{API_KEY_ENV} 환경변수 등록 필요"}
        q = self.quota()
        if not q["ok"]:
            return {"status": "fail", "detail": q.get("error") or "쿼터를 읽지 못했습니다",
                    "code": q.get("http_status")}
        return {"status": "ok", "remain": q["remain"], "total": q["total"],
                "today_used": q["today_used"]}


def carrier_list_url() -> str:
    """17TRACK 캐리어 목록 URL — **오너가 넣기 전엔 빈 문자열**.

    문서는 「JSON/CSV 목록의 `key` 필드가 캐리어 코드」라고만 하고 이 자리에 URL을
    남기지 않았다. **짐작해 박으면 없는 주소를 매일 두드리게 된다.**
    """
    return env_str(CARRIER_LIST_URL_ENV)

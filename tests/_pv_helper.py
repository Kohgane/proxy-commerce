"""Z9(오너 2026-10-09) — 사전검증은 **항상 202 + job_id**다(동기 25초 입구 폐기).

테스트가 예전처럼 결과 dict 하나를 받도록: POST → 잡이 끝날 때까지 `poll`을 묻고 결과를 돌려준다.
POST가 202가 아니면(400·403·503 등) 그 응답 본문을 그대로 돌려준다.
"""
from __future__ import annotations

import time


def prevalidate(client, body: dict, timeout: float = 90.0) -> dict:
    r = client.post("/seller/collect/prevalidate", json=body)
    d = r.get_json() or {}
    if r.status_code != 202:
        d.setdefault("_status", r.status_code)
        return d
    end = time.time() + timeout
    while True:
        _r = client.get(d["poll"])
        if _r.status_code == 429 and time.time() < end:          # 테스트 앱 속도 제한(분당 200) — 화면은 3초 간격이라 해당 없음
            time.sleep(1.0)
            continue
        j = _r.get_json() or {"_status": _r.status_code, "_body": _r.get_data(as_text=True)[:300]}
        if j.get("state") != "running" or time.time() > end:
            rows = j.get("results") or []
            j["all_ok"] = bool(rows) and all(x.get("ok") for x in rows)
            j["job_id"] = d["job_id"]
            return j
        time.sleep(0.4)                                           # 분당 150회 — 테스트 앱 한도(200) 아래

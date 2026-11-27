#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BRANDSEARCH1127 — 오너 11-27 15:18 0-3: 장부 어디에도 없는 셰고가 판매중지 줄을 **브랜드 공식몰**에서 이름으로 찾는다(읽기만 · 큐 덧붙이기만).

읽기: srv_snap/apply_out/relistledger_data_<store>.txt 의 `unmatched`(번호·관리 코드·이름) + `prefix_domain`(같은 관리 코드 앞머리 줄들이 쓰던 가게).
찾기: Shopify 가게 검색 `/search/suggest.json?q=<이름의 영문 낱말>` → 가게 상품 제목 낱말의 70% 이상이 우리 이름에 있는(겹친 낱말 3개+) 상품 → `<상품>.js`(가격·재고) + `/cart.js`(통화).
쓰기: `ops:oneshot:queue`에 `relist_ledger_load`(src=name_match → 앱 화면 「이름 일치(확인 필요)」 — **저절로 켜지 않는다**, 오너가 보고 골라 켬) 덧붙이기 하나뿐.
사용: brand_search_1127.py chezgoga [--dry] [--rebuild]
"""
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from urllib.parse import quote, urlparse

import requests

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
PER = 400
TODAY = (datetime.now(timezone.utc) + timedelta(hours=9)).strftime("%Y-%m-%d")
SQL = ("BEGIN; INSERT INTO app_state (key, value, updated_at) VALUES ('ops:oneshot:queue', '{}'::jsonb, now()) "
       "ON CONFLICT (key) DO NOTHING; "
       "SELECT 1 FROM app_state WHERE key='ops:oneshot:queue' FOR UPDATE; "
       "UPDATE app_state SET value = jsonb_set(value, '{rows}', COALESCE(value->'rows', '[]'::jsonb) || %(row)s::jsonb), "
       "updated_at = now() WHERE key='ops:oneshot:queue' AND NOT EXISTS ("
       "SELECT 1 FROM jsonb_array_elements(COALESCE(value->'rows', '[]'::jsonb)) r "
       "WHERE r->>'op' = 'relist_ledger_load' AND r->>'item_id' = %(item)s); COMMIT;")
STOP = {"the", "and", "for", "with", "of", "a", "an", "in", "x", "by", "edp", "ml", "eau", "de", "parfum", "new"}
S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept": "application/json,text/html,*/*"})
_LAST, _CUR = {}, {}


def _lit(s):
    return "'" + str(s).replace("'", "''") + "'"


def psql(sql):
    r = subprocess.run(["sudo", "-n", "-u", "postgres", "psql", "-d", "gogadb", "-XtAq", "-v", "ON_ERROR_STOP=1", "-f", "-"],
                       input=sql, capture_output=True, text=True, timeout=120)
    return r.stdout.strip() if r.returncode == 0 else ("ERR " + r.stderr.strip()[:300])


def _get(url, timeout=20):
    host = urlparse(url).hostname or ""
    for k in range(4):
        w = 2.5 - (time.time() - _LAST.get(host, 0))
        if w > 0:
            time.sleep(w)
        _LAST[host] = time.time()
        r = S.get(url, timeout=timeout)
        if r.status_code != 429 or k == 3:
            return r
        time.sleep(min(120, int(r.headers.get("Retry-After") or 0) or 20 * (k + 1)))
    return r


def words(name):
    import html as _h
    t = re.sub(r"\[[^\]]*\]", " ", _h.unescape(_h.unescape(str(name or ""))))
    return [w for w in re.findall(r"[A-Za-z][A-Za-z0-9'’\-]{1,}", t) if w.lower() not in STOP]


def overlap(a, b):
    """가게 상품 제목 낱말(b) 중 우리 상품명(a)에 든 비율 — 우리 이름엔 브랜드·꾸밈말이 더 붙어 있어 그쪽 기준으로 잰다. 겹친 낱말 3개 미만이면 0."""
    A, B = {w.lower() for w in a}, {w.lower() for w in b}
    hit = A & B
    return 0.0 if len(hit) < 3 else len(hit) / max(1, len(B))


def search(domain, name):
    ws = words(name)
    if len(ws) < 2:
        return None, "영문 낱말 부족"
    q = " ".join(ws[:6])
    try:
        r = _get(f"https://{domain}/search/suggest.json?q={quote(q)}&resources[type]=product&resources[limit]=5")
        if not r.ok:
            return None, f"검색 HTTP {r.status_code}"
        prods = (((r.json() or {}).get("resources") or {}).get("results") or {}).get("products") or []
    except Exception as e:                                             # noqa: BLE001
        return None, f"검색 실패 {type(e).__name__}"
    best = max(prods, key=lambda p: overlap(ws, words(p.get("title"))), default=None)
    if not best or overlap(ws, words(best.get("title"))) < 0.7:
        return None, "비슷한 상품 없음"
    url = f"https://{domain}" + str(best.get("url") or "").split("?")[0]
    try:
        j = _get(url.rstrip("/") + ".js")
        d = j.json() if j.ok else {}
    except Exception:                                                  # noqa: BLE001
        d = {}
    vs = [v for v in d.get("variants") or [] if isinstance(v, dict)]
    if not vs:
        return None, "가격 못 읽음"
    av = [v for v in vs if v.get("available")]
    price = min(int(v.get("price") or 0) for v in (av or vs)) / 100.0
    if domain not in _CUR:
        try:
            _CUR[domain] = str((_get(f"https://{domain}/cart.js").json() or {}).get("currency") or "")
        except Exception:                                              # noqa: BLE001
            _CUR[domain] = ""
    if price <= 0 or not _CUR[domain]:
        return None, "가격·통화 못 읽음"
    return {"cost": round(price, 2), "currency": _CUR[domain], "url": url, "src_state": "ok" if av else "soldout",
            "via": f"공식몰 검색({domain}) 「{str(best.get('title'))[:60]}」 겹침 {overlap(ws, words(best.get('title'))):.0%}"}, ""


def main(argv):
    try:
        sys.stdout.reconfigure(line_buffering=True)                   # bg 기록에 진행 줄이 바로 보이게(11-27: 4시간 동안 첫 줄뿐)
    except Exception:                                                  # noqa: BLE001
        pass
    if not argv:
        print(__doc__)
        return 2
    store = argv[0]
    kg = os.environ.get("KG_HOME") or "/home1/ikymximy"
    path = os.path.join(kg, "vault", "srv_snap", "apply_out", f"relistledger_data_{store}.txt")
    if not os.path.exists(path):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "srv_snap", "apply_out", f"relistledger_data_{store}.txt")
    doc = json.load(open(path))
    pd = doc.get("prefix_domain") or {}
    todo = doc.get("unmatched") or []
    print(store, "못 찾은 줄", len(todo), "· 앞머리→가게", pd)
    out, why = [], {}
    for r in todo:
        m = re.match(r"^([A-Za-z]+[0-9]?)[-_]", r.get("code") or "")
        dom = r.get("domain") or (pd.get(m.group(1).upper()) if m else None)      # 브랜드 이름으로 찾은 가게 먼저
        if not dom or "amazon." in dom:
            why["가게 모름(앞머리)"] = why.get("가게 모름(앞머리)", 0) + 1
            continue
        got, w = search(dom, r.get("name"))
        if not got:
            why[w] = why.get(w, 0) + 1
            continue
        row = {k: r[k] for k in ("channel_no", "origin_no", "code") if r.get(k)}
        row.update(got, updated=TODAY)
        out.append(row)
    print("찾음", len(out), "/", len(todo), "· 못 찾은 이유", why)
    for x in out[:15]:
        print("  예", json.dumps(x, ensure_ascii=False)[:260])
    if "--dry" in argv or not out:
        print("📌 결과: BRANDSEARCH1127", "(드라이)" if "--dry" in argv else "(넣을 줄 없음)", len(out))
        return 0
    parts = max(1, (len(out) + PER - 1) // PER)
    at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")
    for p in range(parts):
        item = f"{store}:name_match:{p + 1}:{at}"
        row = {"op": "relist_ledger_load", "item_id": item, "store": store, "part": p + 1, "parts": parts, "src": "name_match",
               "rows": out[p * PER:(p + 1) * PER], "rebuild": p == parts - 1 and "--rebuild" in argv, "why": "BRANDSEARCH1127 공식몰 이름 검색",
               "queued_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        res = psql(SQL % {"row": _lit(json.dumps(row, ensure_ascii=False)), "item": _lit(item)})
        print("  조각", p + 1, "/", parts, "→", "줄에 넣음" if not res.startswith("ERR") else res)
    print("📌 결과: BRANDSEARCH1127", store, "이름 일치", len(out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

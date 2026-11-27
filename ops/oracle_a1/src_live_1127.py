#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SRCLIVE1127 — 오너 11-27 15:18 0-3: 셰고가 판매중지 줄의 소싱처 **지금 가격·재고**를 읽어 원가로(출처 「소싱처 실측(날짜)」).

읽기: 볼트 srv_snap/apply_out/relistledger_data_<store>.txt(블루호스트 RELISTLEDGER1127 요약)의 소싱처 주소 줄 전부.
  · Shopify 가게(`/products/<handle>`) → `<주소>.js`(variants 가격·재고) + `/cart.js`(가게 통화) — 공개 JSON.
  · 그 밖 → 페이지의 JSON-LD Offer(price·priceCurrency·availability).
  · 아마존 → 서버에서 막힘(봇 차단) — 「실측 못 함(아마존)」으로만 센다(지어내지 않음).
쓰기: `ops:oneshot:queue`에 `relist_ledger_load`(src=source_live) 덧붙이기 **하나뿐**(허용된 운영 DB 쓰기) · 마지막 조각이 목록 다시 만들기(읽기만).
사용: src_live_1127.py chezgoga [--dry] [--limit N]
"""
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

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


def _lit(s):
    return "'" + str(s).replace("'", "''") + "'"


def psql(sql):
    r = subprocess.run(["sudo", "-n", "-u", "postgres", "psql", "-d", "gogadb", "-XtAq", "-v", "ON_ERROR_STOP=1", "-f", "-"],
                       input=sql, capture_output=True, text=True, timeout=120)
    return r.stdout.strip() if r.returncode == 0 else ("ERR " + r.stderr.strip()[:300])


S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept": "text/html,application/json,*/*", "Accept-Language": "en-US,en;q=0.8"})
_CUR = {}
_LAST = {}


def _pace(host, gap=2.5):
    t = _LAST.get(host, 0)
    w = gap - (time.time() - t)
    if w > 0:
        time.sleep(w)
    _LAST[host] = time.time()


def _get(url, timeout=20):
    """가게마다 2.5초 간격 · 429면 Retry-After(없으면 20·40·60초)만큼 쉬고 최대 3번 다시(11-27 드라이: 1,008 중 699가 429)."""
    host = urlparse(url).hostname or ""
    for k in range(4):
        _pace(host)
        r = S.get(url, timeout=timeout)
        if r.status_code != 429 or k == 3:
            return r
        try:
            w = min(120, int(r.headers.get("Retry-After") or 0)) or 20 * (k + 1)
        except ValueError:
            w = 20 * (k + 1)
        time.sleep(w)
        _LAST[host] = time.time()
    return r


def shop_currency(host):
    if host in _CUR:
        return _CUR[host]
    cur = ""
    try:
        r = _get(f"https://{host}/cart.js", timeout=15)
        if r.ok:
            cur = str((r.json() or {}).get("currency") or "")
    except Exception:                                                  # noqa: BLE001
        cur = ""
    _CUR[host] = cur
    return cur


def read_shopify(url):
    base = url.split("?")[0].split("#")[0].rstrip("/")
    host = urlparse(base).hostname or ""
    r = _get(base + ".js", timeout=20)
    if r.status_code == 404:
        return {"state": "gone", "why": "상품 페이지 404"}
    if not r.ok or "json" not in (r.headers.get("Content-Type") or ""):
        return None
    d = r.json() or {}
    vs = [v for v in d.get("variants") or [] if isinstance(v, dict)]
    if not vs:
        return None
    avail = [v for v in vs if v.get("available")]
    pick = min(avail or vs, key=lambda v: int(v.get("price") or 0))
    price = int(pick.get("price") or 0) / 100.0
    cur = shop_currency(host)
    if price <= 0 or not cur:
        return {"state": "unknown", "why": "가격·통화 못 읽음"}
    return {"cost": round(price, 2), "currency": cur, "state": "ok" if avail else "soldout", "via": "shopify .js"}


def read_jsonld(url):
    r = _get(url, timeout=20)
    if r.status_code in (404, 410):
        return {"state": "gone", "why": f"HTTP {r.status_code}"}
    if not r.ok:
        return {"state": "unknown", "why": f"HTTP {r.status_code}"}
    for blob in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', r.text, re.S | re.I):
        try:
            data = json.loads(blob.strip())
        except Exception:                                              # noqa: BLE001
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            x = stack.pop()
            if isinstance(x, dict):
                if "@graph" in x:
                    stack += x["@graph"] if isinstance(x["@graph"], list) else [x["@graph"]]
                offers = x.get("offers")
                for o in (offers if isinstance(offers, list) else [offers] if offers else []):
                    if isinstance(o, dict) and (o.get("price") or o.get("lowPrice")) and o.get("priceCurrency"):
                        try:
                            p = float(str(o.get("price") or o.get("lowPrice")).replace(",", ""))
                        except ValueError:
                            continue
                        av = str(o.get("availability") or "")
                        st = "soldout" if ("OutOfStock" in av or "SoldOut" in av or "Discontinued" in av) else "ok"
                        return {"cost": round(p, 2), "currency": str(o["priceCurrency"]).upper(), "state": st, "via": "JSON-LD"}
            elif isinstance(x, list):
                stack += x
    return {"state": "unknown", "why": "가격 표기(JSON-LD) 없음"}


def read(url):
    host = (urlparse(url).hostname or "").lower()
    if "amazon." in host:
        return {"state": "unknown", "why": "아마존 — 서버 실측 막힘"}
    try:
        if "/products/" in url:
            got = read_shopify(url)
            if got:
                return got
        return read_jsonld(url)
    except Exception as e:                                             # noqa: BLE001
        return {"state": "unknown", "why": f"열기 실패 {type(e).__name__}"}


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    store = argv[0]
    dry = "--dry" in argv
    lim = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else 0
    kg = os.environ.get("KG_HOME") or "/home1/ikymximy"
    path = os.path.join(kg, "vault", "srv_snap", "apply_out", f"relistledger_data_{store}.txt")
    if not os.path.exists(path):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "srv_snap", "apply_out", f"relistledger_data_{store}.txt")
    doc = json.load(open(path))
    rows = [r for v in (doc.get("parts") or {}).values() for r in v if isinstance(r, dict) and str(r.get("url") or "").startswith("http")]
    seen, todo = set(), []
    for r in rows:
        k = r.get("channel_no") or r.get("origin_no") or r.get("code")
        if k and k not in seen:
            seen.add(k)
            todo.append(r)
    if lim:
        todo = todo[:lim]
    print(store, "소싱처 주소 줄", len(todo), "· 시작", TODAY)
    out, tally, why = [], {}, {}
    for i, r in enumerate(todo):
        got = read(r["url"])
        st = got.get("state")
        tally[st] = tally.get(st, 0) + 1
        if st == "unknown":
            why[got.get("why")] = why.get(got.get("why"), 0) + 1
            continue
        row = {k: r[k] for k in ("channel_no", "origin_no", "code") if r.get(k)}
        row.update(url=r["url"], updated=TODAY, src_state=st, via=got.get("via") or got.get("why") or "")
        if got.get("cost"):
            row.update(cost=got["cost"], currency=got["currency"])
            old = r.get("cost")
            if old and r.get("currency") == got["currency"]:
                d = (got["cost"] - float(old)) / float(old) * 100 if float(old) else 0
                tally["가격 바뀜 ±5%+"] = tally.get("가격 바뀜 ±5%+", 0) + (abs(d) >= 5)
        out.append(row)
        if (i + 1) % 100 == 0:
            print("  진행", i + 1, "/", len(todo), dict(tally))
    print("결과", dict(tally))
    print("못 읽은 이유", dict(sorted(why.items(), key=lambda kv: -kv[1])))
    for x in out[:12]:
        print("  예", json.dumps(x, ensure_ascii=False)[:220])
    if dry or not out:
        print("📌 결과: SRCLIVE1127", "(드라이)" if dry else "(넣을 줄 없음)", len(out))
        return 0
    parts = max(1, (len(out) + PER - 1) // PER)
    at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")
    for p in range(parts):
        chunk = out[p * PER:(p + 1) * PER]
        item = f"{store}:source_live:{p + 1}:{at}"
        row = {"op": "relist_ledger_load", "item_id": item, "store": store, "part": p + 1, "parts": parts, "src": "source_live",
               "rows": chunk, "rebuild": p == parts - 1, "why": "SRCLIVE1127 소싱처 실측",
               "queued_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        res = psql(SQL % {"row": _lit(json.dumps(row, ensure_ascii=False)), "item": _lit(item)})
        print("  조각", p + 1, "/", parts, len(chunk), "줄 →", "줄에 넣음" if not res.startswith("ERR") else res)
    print("📌 결과: SRCLIVE1127", store, "실측", len(out), "줄 · 조각", parts)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SRCLIVE2 — 오너 11-27 15:18 0-3: 셰고가 판매중지 줄의 소싱처 **지금 가격·재고**(출처 「소싱처 실측(날짜)」) — 1판(SRCLIVE1127)의 고친 판.

1판이 12시간 돌고 기록 0줄로 끝났다(출력이 버퍼에 갇힌 채 잡이 끝나 결과를 다 잃음 · Shopify가 IP 단위로 429).
고친 것:
  · Shopify 가게는 상품마다 `.js`(1,008번) 대신 **가게 전체 목록 `/products.json?limit=250&page=N`** 몇 번으로 — 핸들로 맞춘다
    (variants 가격은 소수 문자열 · available 재고). 가게 통화는 `/cart.js` 한 번.
  · 목록에 없는 핸들만 `<주소>.js` 한 번(404 = 내려감).
  · 모든 요청 사이 전체 간격(기본 2.5초 · 가게가 달라도 Shopify는 같은 IP로 막는다) · 429면 Retry-After만큼 쉼.
  · 가게 하나 끝날 때마다 중간 저장(~/kg/ora_state/srclive2_<store>.json) — 다시 띄우면 오늘 읽은 줄은 건너뛴다.
  · 줄 단위 출력(bg 기록에 진행이 바로 보임) · `--max-min N`(기본 100분) 넘으면 멈추고 읽은 만큼만 넣는다.
  · 아마존 = 서버에서 막힘 → 「실측 못 함(아마존)」으로만 센다(지어내지 않음).
쓰기: `ops:oneshot:queue`에 `relist_ledger_load`(src=source_live) 덧붙이기 **하나뿐**(허용된 운영 DB 쓰기) · 마지막 조각이 목록 다시 만들기(읽기만).
사용: src_live2_1127.py chezgoga [--dry] [--no-rebuild] [--max-min N] [--gap 2.5]
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
MAX_PAGES = 40
TODAY = (datetime.now(timezone.utc) + timedelta(hours=9)).strftime("%Y-%m-%d")
SQL = ("BEGIN; INSERT INTO app_state (key, value, updated_at) VALUES ('ops:oneshot:queue', '{}'::jsonb, now()) "
       "ON CONFLICT (key) DO NOTHING; "
       "SELECT 1 FROM app_state WHERE key='ops:oneshot:queue' FOR UPDATE; "
       "UPDATE app_state SET value = jsonb_set(value, '{rows}', COALESCE(value->'rows', '[]'::jsonb) || %(row)s::jsonb), "
       "updated_at = now() WHERE key='ops:oneshot:queue' AND NOT EXISTS ("
       "SELECT 1 FROM jsonb_array_elements(COALESCE(value->'rows', '[]'::jsonb)) r "
       "WHERE r->>'op' = 'relist_ledger_load' AND r->>'item_id' = %(item)s); COMMIT;")

S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept": "application/json,text/html,*/*", "Accept-Language": "en-US,en;q=0.8"})
GAP = [2.5]
_LAST = [0.0]
STATS = {"요청": 0, "429": 0}


def _lit(s):
    return "'" + str(s).replace("'", "''") + "'"


def psql(sql):
    r = subprocess.run(["sudo", "-n", "-u", "postgres", "psql", "-d", "gogadb", "-XtAq", "-v", "ON_ERROR_STOP=1", "-f", "-"],
                       input=sql, capture_output=True, text=True, timeout=120)
    return r.stdout.strip() if r.returncode == 0 else ("ERR " + r.stderr.strip()[:300])


def _get(url, timeout=25):
    """모든 요청 사이 전체 간격 · 429면 Retry-After(없으면 30·60·90초) 쉬고 최대 3번 다시."""
    r = None
    for k in range(4):
        w = GAP[0] - (time.time() - _LAST[0])
        if w > 0:
            time.sleep(w)
        _LAST[0] = time.time()
        STATS["요청"] += 1
        r = S.get(url, timeout=timeout)
        if r.status_code != 429 or k == 3:
            return r
        STATS["429"] += 1
        try:
            w = min(180, int(r.headers.get("Retry-After") or 0)) or 30 * (k + 1)
        except ValueError:
            w = 30 * (k + 1)
        print(f"    429 {urlparse(url).hostname} — {w}초 쉼")
        time.sleep(w)
        _LAST[0] = time.time()
    return r


def handle_of(url):
    m = re.search(r"/products/([^/?#]+)", str(url or ""))
    return re.sub(r"\.js$", "", m.group(1).lower()) if m else ""


def shop_catalog(host):
    """{handle: (최저가(재고 있는 것 우선), 재고 있음?)} · 통화 · 목록 완주했나. JSON이 아니면 None."""
    cat, done = {}, False
    for page in range(1, MAX_PAGES + 1):
        r = _get(f"https://{host}/products.json?limit=250&page={page}")
        if not r.ok or "json" not in (r.headers.get("Content-Type") or ""):
            return (None if page == 1 else cat), "", False, f"products.json HTTP {r.status_code}"
        prods = (r.json() or {}).get("products") or []
        for p in prods:
            vs = [v for v in p.get("variants") or [] if isinstance(v, dict)]
            av = [v for v in vs if v.get("available")]
            prices = []
            for v in (av or vs):
                try:
                    prices.append(float(str(v.get("price") or "0").replace(",", "")))
                except ValueError:
                    pass
            prices = [x for x in prices if x > 0]
            if p.get("handle") and prices:
                cat[str(p["handle"]).lower()] = (round(min(prices), 2), bool(av))
        if len(prods) < 250:
            done = True
            break
    cur = ""
    try:
        c = _get(f"https://{host}/cart.js", timeout=15)
        if c.ok:
            cur = str((c.json() or {}).get("currency") or "")
    except Exception:                                                  # noqa: BLE001
        cur = ""
    return cat, cur, done, ""


def read_js(url, cur):
    base = url.split("?")[0].split("#")[0].rstrip("/")
    r = _get(base + ".js")
    if r.status_code == 404:
        return {"state": "gone", "why": "상품 페이지 404"}
    if not r.ok or "json" not in (r.headers.get("Content-Type") or ""):
        return {"state": "unknown", "why": f".js HTTP {r.status_code}"}
    d = r.json() or {}
    vs = [v for v in d.get("variants") or [] if isinstance(v, dict)]
    av = [v for v in vs if v.get("available")]
    ps = [int(v.get("price") or 0) for v in (av or vs) if int(v.get("price") or 0) > 0]
    if not ps or not cur:
        return {"state": "unknown", "why": "가격·통화 못 읽음"}
    return {"cost": round(min(ps) / 100.0, 2), "currency": cur, "state": "ok" if av else "soldout", "via": "shopify .js"}


def read_jsonld(url):
    r = _get(url)
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
            if isinstance(x, list):
                stack += x
                continue
            if not isinstance(x, dict):
                continue
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
    return {"state": "unknown", "why": "가격 표기(JSON-LD) 없음"}


def rowkey(r):
    return str(r.get("channel_no") or r.get("origin_no") or r.get("code") or "")


def load_rows(store):
    kg = os.environ.get("KG_HOME") or "/home1/ikymximy"
    path = os.path.join(kg, "vault", "srv_snap", "apply_out", f"relistledger_data_{store}.txt")
    if not os.path.exists(path):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "srv_snap", "apply_out", f"relistledger_data_{store}.txt")
    doc = json.load(open(path))
    rows = [r for v in (doc.get("parts") or {}).values() for r in v if isinstance(r, dict) and str(r.get("url") or "").startswith("http")]
    seen, todo = set(), []
    for r in rows:
        k = rowkey(r)
        if k and k not in seen:
            seen.add(k)
            todo.append(r)
    return todo


def main(argv):
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:                                                  # noqa: BLE001
        pass
    if not argv:
        print(__doc__)
        return 2
    store = argv[0]
    dry = "--dry" in argv
    max_min = float(argv[argv.index("--max-min") + 1]) if "--max-min" in argv else 100.0
    if "--gap" in argv:
        GAP[0] = float(argv[argv.index("--gap") + 1])
    t0 = time.time()
    kg = os.environ.get("KG_HOME") or os.path.expanduser("~")
    os.makedirs(os.path.join(kg, "ora_state"), exist_ok=True)
    ck_path = os.path.join(kg, "ora_state", f"srclive2_{store}.json")
    try:
        ck = json.load(open(ck_path))
    except Exception:                                                  # noqa: BLE001
        ck = {}
    if ck.get("day") != TODAY:
        ck = {"day": TODAY, "rows": {}}
    done = ck["rows"]
    todo = load_rows(store)
    by_host = {}
    for r in todo:
        by_host.setdefault((urlparse(r["url"]).hostname or "").lower(), []).append(r)
    print(store, "소싱처 주소 줄", len(todo), "· 가게", len(by_host), "· 오늘 이미 읽은 줄", len(done), "· 시작", TODAY)
    stopped = ""
    for hi, (host, rs) in enumerate(sorted(by_host.items(), key=lambda kv: -len(kv[1]))):
        left = [r for r in rs if rowkey(r) not in done]
        if not left:
            continue
        if (time.time() - t0) / 60 > max_min:
            stopped = f"{max_min:.0f}분 넘음 — 가게 {len(by_host) - hi}곳 남김"
            break
        if "amazon." in host:
            for r in left:
                done[rowkey(r)] = {"state": "unknown", "why": "아마존 — 서버 실측 막힘"}
            continue
        try:
            shop = [r for r in left if "/products/" in r["url"]]
            other = [r for r in left if "/products/" not in r["url"]]
            if shop:
                cat, cur, complete, why = shop_catalog(host)
                miss = []
                for r in shop:
                    h = handle_of(r["url"])
                    if cat is not None and h in cat and cur:
                        price, av = cat[h]
                        done[rowkey(r)] = {"cost": price, "currency": cur, "state": "ok" if av else "soldout", "via": "shopify products.json"}
                    else:
                        miss.append(r)
                for r in miss:                                         # 목록에 없거나 목록 못 읽음 → 그 상품만 한 번
                    done[rowkey(r)] = read_js(r["url"], cur) if cur or cat is None else {"state": "unknown", "why": "가게 통화 못 읽음"}
                    if done[rowkey(r)].get("state") == "unknown" and cat is None:
                        done[rowkey(r)] = read_jsonld(r["url"])
                print(f"  {host}: {len(shop)}줄 · 목록 {len(cat or {})}개{'(완주)' if complete else ''} {why} · 따로 읽음 {len(miss)} · 통화 {cur or '?'}")
            for r in other:
                done[rowkey(r)] = read_jsonld(r["url"])
            if other:
                print(f"  {host}: 그 밖 {len(other)}줄(JSON-LD)")
        except Exception as e:                                         # noqa: BLE001
            print(f"  {host}: 열기 실패 {type(e).__name__} — 다음 가게")
            for r in left:
                done.setdefault(rowkey(r), {"state": "unknown", "why": f"열기 실패 {type(e).__name__}"})
        json.dump(ck, open(ck_path + ".tmp", "w"), ensure_ascii=False)
        os.replace(ck_path + ".tmp", ck_path)
    tally, why = {}, {}
    out = []
    for r in todo:
        got = done.get(rowkey(r))
        if not got:
            tally["안 읽음(시간)"] = tally.get("안 읽음(시간)", 0) + 1
            continue
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
            try:
                if old and r.get("currency") == got["currency"] and abs(got["cost"] - float(old)) / float(old) >= 0.05:
                    tally["가격 바뀜 ±5%+"] = tally.get("가격 바뀜 ±5%+", 0) + 1
            except (TypeError, ValueError, ZeroDivisionError):
                pass
        out.append(row)
    print("결과", tally, "· 요청", STATS, "·", f"{(time.time() - t0) / 60:.0f}분", "·", stopped or "끝까지")
    print("못 읽은 이유", dict(sorted(why.items(), key=lambda kv: -kv[1])))
    for x in out[:12]:
        print("  예", json.dumps(x, ensure_ascii=False)[:220])
    if dry or not out:
        print("📌 결과: SRCLIVE2", "(드라이 — 중간 저장만, 다음 실행이 이어씀)" if dry else "(넣을 줄 없음)", len(out))
        return 0
    parts = max(1, (len(out) + PER - 1) // PER)
    at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")
    for p in range(parts):
        chunk = out[p * PER:(p + 1) * PER]
        item = f"{store}:source_live:{p + 1}:{at}"
        row = {"op": "relist_ledger_load", "item_id": item, "store": store, "part": p + 1, "parts": parts, "src": "source_live",
               "rows": chunk, "rebuild": p == parts - 1 and "--no-rebuild" not in argv, "why": "SRCLIVE2 소싱처 실측",
               "queued_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        res = psql(SQL % {"row": _lit(json.dumps(row, ensure_ascii=False)), "item": _lit(item)})
        print("  조각", p + 1, "/", parts, len(chunk), "줄 →", "줄에 넣음" if not res.startswith("ERR") else res)
    print("📌 결과: SRCLIVE2", store, "실측", len(out), "줄 · 조각", parts)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

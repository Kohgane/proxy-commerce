# -*- coding: utf-8 -*-
"""BRANDCAT1128 — 오너 11-28 감독 3: 원가를 끝까지 못 찾은 셰고가 줄을 **브랜드 공식몰 전체 목록**에서 품번·이름으로 찾는다(조회만 · DB 쓰기 0).

어제(BRANDSEARCH1127)는 가게 검색창(`search/suggest.json`)에 물어 3/428 — 검색 403·가격 못 읽음(오라클 IP 막힘)이 159였다.
이번엔 블루호스트 IP로 **가게 전체 목록**(`/products.json?limit=250&page=N` · `localization=US` 쿠키 = 장부 USD 시장)을 한 번 받아
  ① **품번 일치** — 우리 상품명·관리 코드 속 품번(숫자가 든 6자 이상 토큰 · 예 994-25002)이 가게 상품 제목·핸들·SKU에 **정확히 하나** → `code`
  ② **이름 일치** — 가게 제목 낱말의 70% 이상이 우리 이름에 있고 겹친 낱말 3개+ → `name`(앱에서 「이름 일치(확인 필요)」 · 저절로 안 켬)
결과는 볼트 srv_snap/apply_out/brandcat_data_<store>.txt(내용 JSON) — 오라클이 큐에 넣는다(`brand_catalog_push`).
가게(도메인) = 줄에 붙은 것 → 관리 코드 앞머리가 쓰던 가게 → BRANDS 표(아래 · 오너 지목 앞머리). 사용: brand_catalog_1128.py chezgoga [--max-min 11]
"""
import html as _h
import json
import os
import re
import sys
import time
import urllib.error as UE
import urllib.request as U
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
H = os.environ.get("KG_HOME") or ("/home1/ikymximy" if os.path.isdir("/home1/ikymximy") else os.path.expanduser("~"))
TODAY = (datetime.now(timezone.utc) + timedelta(hours=9)).strftime("%Y-%m-%d")
#: 오너 지목 앞머리 → 공식몰(Shopify만 — 전체 목록을 받을 수 있는 곳). 포터(요시다카반)는 Shopify가 아니라 오라클 쪽에서 따로.
BRANDS = {"CL7": "cloud7.de", "FMA": "foundmyanimal.com", "ROVYVON": "rovyvon.com", "AURORA": "rovyvon.com"}
STOP = {"the", "and", "for", "with", "of", "a", "an", "in", "x", "by", "edp", "ml", "eau", "de", "parfum", "new", "amp"}
_LAST = [0.0]
COOKIE = "localization=US"


def get(url, timeout=25):
    w = 2.5 - (time.time() - _LAST[0])
    if w > 0:
        time.sleep(w)
    _LAST[0] = time.time()
    try:
        with U.urlopen(U.Request(url, headers={"User-Agent": UA, "Accept": "application/json", "Cookie": COOKIE}), timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8", "replace"))
    except UE.HTTPError as e:
        return e.code, None
    except Exception as e:                                             # noqa: BLE001
        return type(e).__name__, None


def words(name):
    t = re.sub(r"\[[^\]]*\]", " ", _h.unescape(_h.unescape(str(name or ""))))
    return [w for w in re.findall(r"[A-Za-z][A-Za-z0-9'’\-]{1,}", t) if w.lower() not in STOP]


def codes_in(*texts):
    """품번 후보 — 숫자가 든 6자 이상 토큰(하이픈 포함 · 예 994-25002 · 622-19859). 관리 코드의 앞머리·일련번호는 뺌."""
    out = set()
    for t in texts:
        for m in re.findall(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+|\d{6,}", str(t or "")):
            if len(m) >= 6 and re.search(r"\d", m):
                out.add(m.upper())
    return {c for c in out if not re.match(r"^(CL7|FMA|PT|TOSU|CRG|KM|IA|CP|ROVYVON|AURORA)-", c)}


def overlap(a, b):
    A, B = {w.lower() for w in a}, {w.lower() for w in b}
    hit = A & B
    return 0.0 if len(hit) < 3 else len(hit) / max(1, len(B))


def catalog(dom):
    prods, page = [], 1
    while page <= 40:
        st, j = get(f"https://{dom}/products.json?limit=250&page={page}")
        if st != 200 or not isinstance(j, dict):
            return prods, f"products.json HTTP {st}"
        ps = j.get("products") or []
        prods += ps
        if len(ps) < 250:
            break
        page += 1
    return prods, ""


def main(argv):
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:                                                  # noqa: BLE001
        pass
    store = argv[0] if argv else "chezgoga"
    max_min = float(argv[argv.index("--max-min") + 1]) if "--max-min" in argv else 11.0
    t0 = time.time()
    doc = json.load(open(os.path.join(H, "vault", "srv_snap", "apply_out", f"relistledger_data_{store}.txt")))
    pd = {k.upper(): v for k, v in (doc.get("prefix_domain") or {}).items()}
    todo = doc.get("unmatched") or []
    by_dom, why = {}, {}
    for r in todo:
        m = re.match(r"^([A-Za-z]+[0-9]?)[-_]", r.get("code") or "")
        pre = m.group(1).upper() if m else ""
        dom = BRANDS.get(pre) or r.get("domain") or pd.get(pre)
        if not dom or "amazon." in str(dom) or "yoshidakaban" in str(dom):
            why["가게 모름·Shopify 아님(포터는 오라클 따로)"] = why.get("가게 모름·Shopify 아님(포터는 오라클 따로)", 0) + 1
            continue
        by_dom.setdefault(dom.lower(), []).append(r)
    print(store, "못 찾은 줄", len(todo), "· 가게", len(by_dom), "· 시작", TODAY)
    out = []
    for dom, rs in sorted(by_dom.items(), key=lambda kv: -len(kv[1])):
        if (time.time() - t0) / 60 > max_min:
            why["시간(다음 회차)"] = why.get("시간(다음 회차)", 0) + len(rs)
            continue
        prods, err = catalog(dom)
        st, cart = get(f"https://{dom}/cart.js")
        cur = str((cart or {}).get("currency") or "") if st == 200 else ""
        if not prods or not cur:
            why[f"목록·통화 못 읽음({err or 'cart'})"] = why.get(f"목록·통화 못 읽음({err or 'cart'})", 0) + len(rs)
            print(f"  {dom}: {len(rs)}줄 — 목록 {len(prods)} · 통화 {cur or '?'} {err}")
            continue
        idx = []
        for p in prods:
            vs = [v for v in p.get("variants") or [] if isinstance(v, dict)]
            av = [v for v in vs if v.get("available")]
            pr = [float(str(v.get("price") or "0").replace(",", "")) for v in (av or vs) if str(v.get("price") or "").strip()]
            pr = [x for x in pr if x > 0]
            if not pr:
                continue
            blob = " ".join([str(p.get("title") or ""), str(p.get("handle") or "")] + [str(v.get("sku") or "") for v in vs]).upper()
            idx.append({"title": str(p.get("title") or ""), "handle": str(p.get("handle") or ""), "blob": blob,
                        "price": round(min(pr), 2), "av": bool(av), "w": words(p.get("title"))})
        n_code = n_name = 0
        for r in rs:
            cs = codes_in(r.get("name"), r.get("code"))
            hit = [p for p in idx if cs and any(c in p["blob"] for c in cs)]
            kind = ""
            if len(hit) == 1:
                p, kind = hit[0], "code"
            else:
                ws = words(r.get("name"))
                best = max(idx, key=lambda p: overlap(ws, p["w"]), default=None)
                if best and overlap(ws, best["w"]) >= 0.7:
                    p, kind = best, "name"
            if not kind:
                why["비슷한 상품 없음" if not hit else f"품번이 {len(hit)}개에 맞음(못 정함)"] = \
                    why.get("비슷한 상품 없음" if not hit else f"품번이 {len(hit)}개에 맞음(못 정함)", 0) + 1
                continue
            row = {k: r[k] for k in ("channel_no", "origin_no", "code") if r.get(k)}
            row.update(cost=p["price"], currency=cur, url=f"https://{dom}/products/{p['handle']}", updated=TODAY,
                       src_state="ok" if p["av"] else "soldout", kind=kind,
                       via=(f"공식몰 품번 일치({dom} · {', '.join(sorted(cs))[:40]})" if kind == "code"
                            else f"공식몰 목록 이름 일치({dom}) 「{p['title'][:50]}」 {overlap(words(r.get('name')), p['w']):.0%}"))
            out.append(row)
            n_code += kind == "code"
            n_name += kind == "name"
        print(f"  {dom}: {len(rs)}줄 · 목록 {len(idx)}개 · 통화 {cur} · 품번 일치 {n_code} · 이름 일치 {n_name}")
    dst = os.path.join(H, "vault", "srv_snap", "apply_out", f"brandcat_data_{store}.txt")
    json.dump({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "day": TODAY, "rows": out}, open(dst + ".tmp", "w"), ensure_ascii=False)
    os.replace(dst + ".tmp", dst)
    print("찾음", len(out), "/", len(todo), "· 품번", sum(1 for x in out if x["kind"] == "code"), "· 이름", sum(1 for x in out if x["kind"] == "name"),
          "· 못 찾은 이유", why)
    for x in out[:12]:
        print("  예", json.dumps(x, ensure_ascii=False)[:240])
    print("📌 결과: BRANDCAT1128", store, len(out), "줄을 볼트 파일에(DB 쓰기 0)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

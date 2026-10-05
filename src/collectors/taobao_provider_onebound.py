"""Z3-B(오너 2026-10-05) — 타오바오 상세 외부 공급자 **온바운드(万邦) item_get**.

    GET https://api-gw.onebound.cn/taobao/item_get/
        key=ONEBOUND_KEY · secret=ONEBOUND_SECRET · num_iid=<상품번호> · is_promotion=1 · lang=zh-CN
    단가 0.023元/회(체험 키: 일 10회 · 2026-10-08까지 — 응답 api_info로 확인).

- `lang`은 바꾸지 않는다(다른 값은 번역 과금). 번역은 우리 체인(Papago·텐센트).
- 타임아웃 15초, 재시도는 **5xx·타임아웃만 1회**. 4xx·error_code≠"0000"은 재시도 0.
- 한도 `ONEBOUND_DAILY_CAP`(기본 60, 계정 전체) — 넘으면 **호출 전에** 「온바운드 일일 한도」.
- 원문 JSON은 상품당 최신 1건 보관(재파싱·분쟁 대비). 같은 상품을 24시간 안에 다시 담으면 **보관본 재사용**(호출 0) —
  진단의 「새로 받기」만 재호출.
- 캐시: 응답 `cache`=1이고 `data_update`가 하루 넘게 지났으면 「가격 기준 {data_update}」를 카드에 적는다.
  캐시 우회 파라미터는 문서(open.onebound.cn — 이 컨테이너 egress 차단)에서 이름을 확인 못 해 **쓰지 않는다**(추측 금지).

필드 매핑은 오너 지시(2026-10-05, 실측 응답 기준)를 그대로 따른다 — `normalize` 주석. 출력은 기존 getdetail 파서
(`taobao_mtop.enrich_payload`)와 같은 키 + 공급자 전용 칸(`provider` 아래) → 뒤 파이프라인은 그대로.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

ENDPOINT = "https://api-gw.onebound.cn/taobao/item_get/"
ENV_KEY, ENV_SECRET, ENV_CAP = "ONEBOUND_KEY", "ONEBOUND_SECRET", "ONEBOUND_DAILY_CAP"
DEFAULT_CAP = 60
UNIT_PRICE = "0.023元/회"
TIMEOUT = 15
REUSE_HOURS = 24
_KST = timezone(timedelta(hours=9))
_RAW = "onebound:raw:"           # + num_iid → {raw, at, bytes, ms}
_LAST = "onebound:last"          # 마지막으로 받은 상품번호(진단 내려받기)
_PIXEL = re.compile(r"(?:^|//)(?:[\w-]+\.)*o0b\.cn/", re.I)        # 추적 픽셀(i.php?t.png…)


# ── 설정 ───────────────────────────────────────────────────────────────────────

def keys_missing() -> List[str]:
    return [k for k in (ENV_KEY, ENV_SECRET) if not os.getenv(k, "").strip()]


def daily_cap() -> int:
    try:
        return max(0, int(os.getenv(ENV_CAP, str(DEFAULT_CAP)).strip() or DEFAULT_CAP))
    except ValueError:
        return DEFAULT_CAP


def _day_key(now=None) -> str:
    return "onebound_calls:" + (now or datetime.now(timezone.utc)).astimezone(_KST).strftime("%Y-%m-%d")


def used_today() -> int:
    from src.db import option_translate_queue_pg as q
    return q.day_count(_day_key())


def _take() -> bool:
    from src.db import option_translate_queue_pg as q
    granted, _n = q.take_n(_day_key(), daily_cap(), 1)
    return granted >= 1


def parse_api_info(s: Any) -> Dict[str, Any]:
    """`"today: max:10 all[=++];expires:2026-10-08"` → `{max: 10, expires: "2026-10-08"}`. 못 읽으면 빈 칸(호출은 계속)."""
    s = str(s or "")
    m = re.search(r"max\s*:\s*(\d+)", s)
    e = re.search(r"expires\s*:\s*(\d{4}-\d{2}-\d{2})", s)
    return {"max": int(m.group(1)) if m else None, "expires": e.group(1) if e else "", "raw": s[:120]}


def mask(raw: Any) -> Any:
    """진단 화면용 — 키·시크릿 값이 어디에 섞여 와도 글자 수로 가린다(이름에 key/secret/token인 칸도)."""
    secrets = [v for v in (os.getenv(ENV_KEY, "").strip(), os.getenv(ENV_SECRET, "").strip()) if v]

    def walk(x):
        if isinstance(x, dict):
            return {k: (f"<{len(str(v))}자 가림>" if re.fullmatch(r"(?i)(api_?)?(key|secret|token)", str(k)) and isinstance(v, str)
                        else walk(v)) for k, v in x.items()}
        if isinstance(x, list):
            return [walk(v) for v in x]
        if isinstance(x, str):
            for sec in secrets:
                x = x.replace(sec, f"<{len(sec)}자 가림>")
        return x
    return walk(raw)


# ── 정규화 ─────────────────────────────────────────────────────────────────────

def _https(u: Any) -> str:
    u = str(u or "").strip()
    return "https:" + u if u.startswith("//") else u


def _float(v: Any) -> Optional[float]:
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _int(v: Any) -> Optional[int]:
    try:
        return int(float(str(v).strip()))
    except (TypeError, ValueError):
        return None


def _truthy(v: Any) -> bool:
    return v is True or str(v).strip().lower() in ("1", "true", "yes")


def _dedup(urls) -> List[str]:
    out, seen = [], set()
    for u in urls:
        u = _https(u)
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _stale(data_update: str, now=None) -> bool:
    """`data_update`가 하루 넘게 지났나. 못 읽으면 True(기준 날짜를 보이는 편이 안전)."""
    s = str(data_update or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            t = datetime.strptime(s[:19], fmt).replace(tzinfo=_KST)
            return (now or datetime.now(timezone.utc)) - t > timedelta(days=1)
        except ValueError:
            continue
    return True


def normalize(raw: dict, now=None) -> Dict[str, Any]:
    """온바운드 item_get → `enrich_payload` 키(title·images·options·skus·price·currency·detail_images·source_path)
    + 공급자 칸. 매핑(오너 지시):

      item.title → title · item.price / orginal_price → price_cny / original_price_cny(float)
      item.pic_url + item_imgs[].url → images(「//」 → https:) · item.desc_img[] → desc_images(o0b.cn 픽셀·Y1 쓰레기 제외)
      item.desc(html) → 파싱 안 함(원문 보관본에 있음) · item.props[]{name,value} → spec_table(= detail_specs [이름, 값])
      item.props_list{"pid:vid": "축:값"} + skus.sku[]{price, quantity, properties "pid:vid;pid:vid", sku_id}
        → 축별 값 + SKU 조합별 가격·재고(properties_name은 안 씀) · prop_imgs.prop_img[] → 옵션값 사진
      item.video.url → video_url(보관만) · location → origin_city(표기만) · tmall → is_tmall
      seller_info.shop_name / nick → shop_name · num → stock_total(sales·total_sold는 안 믿음)
    """
    from src.collectors.collect_status import real_detail_images
    item = (raw or {}).get("item") or {}
    notes: List[str] = []
    imgs = _dedup([item.get("pic_url")] + [x.get("url") for x in (item.get("item_imgs") or []) if isinstance(x, dict)])
    desc = [u for u in _dedup(u for u in (item.get("desc_img") or []) if isinstance(u, str)) if not _PIXEL.search(u)]
    desc = real_detail_images(desc)
    plist = item.get("props_list") if isinstance(item.get("props_list"), dict) else {}
    pv_name: Dict[str, tuple] = {}
    axes: Dict[str, List[str]] = {}
    for pv, label in plist.items():
        name, sep, val = str(label).partition(":")
        if not sep:
            notes.append(f"props_list 값에 「축:값」 아님 — {str(label)[:30]}")
            continue
        name, val = name.strip(), val.strip()
        pv_name[str(pv).strip()] = (name, val)
        vals = axes.setdefault(name, [])
        if val not in vals:
            vals.append(val)
    skus = []
    sku_rows = (item.get("skus") or {}).get("sku") if isinstance(item.get("skus"), dict) else None
    if item.get("skus") and not isinstance(sku_rows, list):
        notes.append("skus 모양이 {sku:[…]}가 아님 — SKU 안 읽음")
    for k in sku_rows or []:
        if not isinstance(k, dict):
            continue
        spec, miss = [], []
        for pv in str(k.get("properties") or "").split(";"):
            pv = pv.strip()
            if not pv:
                continue
            if pv in pv_name:
                spec.append(pv_name[pv][1])
            else:
                miss.append(pv)
        if miss:
            notes.append(f"SKU {k.get('sku_id')}: props_list에 없는 속성 {', '.join(miss)[:40]}")
        p = _float(k.get("price"))
        skus.append({"spec": spec, "price": "" if p is None else p, "stock": _int(k.get("quantity")),
                     "sku_id": str(k.get("sku_id") or "")})
    opt_imgs = {}
    pimg = (item.get("prop_imgs") or {}).get("prop_img") if isinstance(item.get("prop_imgs"), dict) else None
    # ★ prop_img 원소의 키(`properties`·`url`)는 오너 지시에 이름이 없어 **실응답 픽스처로 확인 전** — 둘 다 있을 때만 읽는다.
    for x in pimg or []:
        if isinstance(x, dict) and x.get("properties") in pv_name and x.get("url"):
            opt_imgs[pv_name[x["properties"]][1]] = _https(x["url"])
    spec_table = [[str(p.get("name") or "").strip(), str(p.get("value") or "").strip()]
                  for p in (item.get("props") or []) if isinstance(p, dict) and str(p.get("name") or "").strip()]
    price = _float(item.get("price"))
    if price is None:
        notes.append("item.price 숫자 아님")
    seller = item.get("seller_info") if isinstance(item.get("seller_info"), dict) else {}
    video = item.get("video")
    cache = _truthy((raw or {}).get("cache"))
    data_update = str((raw or {}).get("data_update") or item.get("data_update") or "")
    provider = {
        "name": "onebound", "price_cny": price, "original_price_cny": _float(item.get("orginal_price")),
        "desc_images": desc, "spec_table": spec_table, "option_images": opt_imgs,
        "video_url": _https(video.get("url")) if isinstance(video, dict) else "",
        "origin_city": str(item.get("location") or ""), "is_tmall": _truthy(item.get("tmall")),
        "shop_name": str(seller.get("shop_name") or item.get("nick") or ""), "stock_total": _int(item.get("num")),
        "cache": cache, "data_update": data_update,
        "price_asof": data_update if (cache and _stale(data_update, now)) else "",
        "api_info": parse_api_info((raw or {}).get("api_info")), "parse_notes": notes,
    }
    return {"title": str(item.get("title") or ""), "images": imgs,
            "options": [{"name": n, "values": v} for n, v in axes.items()], "skus": skus,
            "price": price if price is not None else "", "currency": "CNY", "detail_images": desc,
            "detail_specs": spec_table, "shop_name": provider["shop_name"], "source_path": "onebound",
            "provider": provider}


# ── 보관 ───────────────────────────────────────────────────────────────────────

def stored(num_iid: str) -> Dict[str, Any]:
    from src.db import image_translate_queue_pg as st
    return st.state_get(_RAW + str(num_iid)) or {}


def _store(num_iid: str, raw: dict, nbytes: int, ms: int) -> None:
    from src.db import image_translate_queue_pg as st
    st.state_set(_RAW + str(num_iid), {"raw": raw, "at": datetime.now(timezone.utc).isoformat(), "bytes": nbytes, "ms": ms})
    st.state_set(_LAST, {"num_iid": str(num_iid)})


def last_num_iid() -> str:
    from src.db import image_translate_queue_pg as st
    return str((st.state_get(_LAST) or {}).get("num_iid") or "")


def _fresh(rec: dict, now=None) -> bool:
    try:
        at = datetime.fromisoformat(str(rec.get("at")))
        return (now or datetime.now(timezone.utc)) - at < timedelta(hours=REUSE_HOURS)
    except Exception:
        return False


# ── 호출 ───────────────────────────────────────────────────────────────────────

def _get(params: dict, transport=None):
    """`(status, text)` — 5xx·타임아웃만 1회 재시도."""
    import requests
    last_exc = None
    for attempt in (1, 2):
        try:
            if transport is not None:
                status, text = transport(ENDPOINT, params)
            else:
                r = requests.get(ENDPOINT, params=params, timeout=TIMEOUT)
                status, text = r.status_code, r.text or ""
        except requests.exceptions.Timeout as exc:
            last_exc = exc
            if attempt == 1:
                continue
            raise
        if 500 <= int(status) < 600 and attempt == 1:
            continue
        return status, text
    raise last_exc or RuntimeError("재시도 뒤에도 응답 없음")


def call(num_iid: str, *, refresh: bool = False, transport=None) -> Dict[str, Any]:
    """`{ok, kind, why, raw, ms, bytes, reused}`. 24시간 안 보관본이 있으면 재사용(refresh=True면 재호출)."""
    iid = str(num_iid or "").strip()
    if not iid:
        return {"ok": False, "kind": "provider_fail", "why": "상품번호 해석 실패", "raw": None, "ms": 0, "bytes": 0}
    rec = stored(iid)
    if rec.get("raw") and not refresh and _fresh(rec):
        return {"ok": True, "kind": "ok", "why": "", "raw": rec["raw"], "ms": 0, "bytes": int(rec.get("bytes") or 0),
                "reused": True, "at": rec.get("at")}
    miss = keys_missing()
    if miss:
        return {"ok": False, "kind": "provider_fail", "why": "공급자 키 미설정 — " + " · ".join(miss), "raw": None,
                "ms": 0, "bytes": 0}
    if not _take():
        return {"ok": False, "kind": "provider_cap",
                "why": f"온바운드 일일 한도 — 오늘 {daily_cap()}회 다 씀(ONEBOUND_DAILY_CAP), 내일 다시", "raw": None,
                "ms": 0, "bytes": 0}
    params = {"key": os.getenv(ENV_KEY, "").strip(), "secret": os.getenv(ENV_SECRET, "").strip(),
              "num_iid": iid, "is_promotion": "1", "lang": "zh-CN"}
    t0 = time.monotonic()
    try:
        status, text = _get(params, transport)
    except Exception as exc:                                    # noqa: BLE001
        ms = int((time.monotonic() - t0) * 1000)
        logger.info("[onebound] num_iid=%s 실패 %s · %dms", iid, type(exc).__name__, ms)
        return {"ok": False, "kind": "provider_fail", "why": f"온바운드 요청 실패 {type(exc).__name__}", "raw": None,
                "ms": ms, "bytes": 0}
    ms, nbytes = int((time.monotonic() - t0) * 1000), len(str(text).encode("utf-8"))
    try:
        raw = json.loads(text)
    except Exception:
        raw = None
    code = str((raw or {}).get("error_code") or "") if isinstance(raw, dict) else ""
    logger.info("[onebound] num_iid=%s HTTP %s · error_code=%s · cache=%s · execution_time=%s · %d바이트 · %dms",
                iid, status, code or "—", (raw or {}).get("cache") if isinstance(raw, dict) else "—",
                (raw or {}).get("execution_time") if isinstance(raw, dict) else "—", nbytes, ms)
    if not isinstance(raw, dict):
        return {"ok": False, "kind": "provider_fail", "why": f"온바운드 HTTP {status} · JSON 아닌 응답({nbytes}바이트)",
                "raw": None, "ms": ms, "bytes": nbytes}
    if code != "0000" or not isinstance(raw.get("item"), dict):
        said = str(raw.get("reason") or raw.get("error") or "").strip()            # 원문 그대로(번역 안 함)
        return {"ok": False, "kind": "provider_fail", "why": f"온바운드 {code or '응답 코드 없음'}" + (f": {said[:160]}" if said else ""),
                "raw": raw, "ms": ms, "bytes": nbytes}
    _store(iid, raw, nbytes, ms)
    return {"ok": True, "kind": "ok", "why": "", "raw": raw, "ms": ms, "bytes": nbytes, "reused": False}


def fetch_detail(num_iid: str, *, refresh: bool = False, transport=None) -> Dict[str, Any]:
    """`taobao_mtop.fetch`와 같은 모양 — `{state: ok|manual, kind, reason, payload, raw, ms, bytes, reused}`."""
    c = call(num_iid, refresh=refresh, transport=transport)
    base = {"raw": c.get("raw"), "ms": c.get("ms", 0), "bytes": c.get("bytes", 0), "reused": bool(c.get("reused"))}
    if not c["ok"]:
        return {"state": "manual", "kind": c["kind"], "reason": c["why"], "payload": None, **base}
    payload = normalize(c["raw"])
    if not (payload["title"] and payload["images"]):
        return {"state": "manual", "kind": "provider_fail", "reason": "온바운드 응답에 제목·사진이 비었어요", "payload": None, **base}
    return {"state": "ok", "kind": "ok", "reason": "", "payload": payload, **base}

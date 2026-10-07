"""Z3-B(오너 2026-10-05) — 타오바오 상세 외부 공급자 **온바운드(万邦) item_get**.

    GET https://api-gw.onebound.cn/taobao/item_get/
        key=ONEBOUND_KEY · secret=ONEBOUND_SECRET · num_iid=<상품번호> · is_promotion=1 · lang=zh-CN
    단가 0.023元/회(체험 키: 일 10회 · 2026-10-08까지 — 응답 api_info로 확인).

- `lang`은 바꾸지 않는다(다른 값은 번역 과금). 번역은 우리 체인(Papago·텐센트).
- 타임아웃 15초, 재시도는 **5xx·타임아웃만 1회**. 4xx·error_code≠"0000"은 재시도 0.
- 한도 `ONEBOUND_DAILY_CAP`(기본 60, 계정 전체) — 넘으면 **호출 전에** 「온바운드 일일 한도」.
- 원문 JSON은 상품당 최신 1건 보관(재파싱·분쟁 대비). 같은 상품을 24시간 안에 다시 담으면 **보관본 재사용**(호출 0) —
  진단의 「새로 받기」만 재호출(`cache=no`, 보관본을 덮어씀).
- 캐시 우회 = **`cache=no`**(오너 실측 2026-10-05 — 테스트 페이지 「캐시 업데이트」의 Request address. 기본은 미지정 = 캐시 허용).
  자동 경로는 응답 `cache`=1이고 `data_update`(베이징 시각)가 24시간 넘었을 때만 `cache=no`로 **1회** 재호출(한도 1회로 셈).
  그 재호출이 실패하면 받은 캐시 값을 쓰고 카드에 「가격 기준 {data_update}」.
  `ONEBOUND_REFRESH_STALE`(기본 1)=0이면 이 자동 재호출을 하지 않는다(체험 기간 10/8 전엔 오너가 0으로 둠).

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
ENV_REFRESH_STALE = "ONEBOUND_REFRESH_STALE"
DEFAULT_CAP = 60
UNIT_PRICE = "0.023元/회"
TIMEOUT = 15
REUSE_HOURS = 24
_KST = timezone(timedelta(hours=9))
_CST = timezone(timedelta(hours=8))            # 온바운드 data_update·server_time은 베이징 시각
_RAW = "onebound:raw:"           # + num_iid → {raw, at, bytes, ms}
_LAST = "onebound:last"          # 마지막으로 받은 상품번호(진단 내려받기)
_PIXEL = re.compile(r"(?:^|//)(?:[\w-]+\.)*o0b\.cn/", re.I)        # 추적 픽셀(i.php?t.png…)


# ── 설정 ───────────────────────────────────────────────────────────────────────

def keys_missing() -> List[str]:
    return [k for k in (ENV_KEY, ENV_SECRET) if not os.getenv(k, "").strip()]


def refresh_stale() -> bool:
    """`ONEBOUND_REFRESH_STALE`(기본 1) — 0이면 하루 넘은 캐시여도 자동 `cache=no` 재호출을 하지 않는다
    (체험 키 일 10회 동안 오너가 0으로 둠 — 2026-10-08까지). 「새로 받기」(진단)는 이 값과 무관하게 `cache=no`."""
    return os.getenv(ENV_REFRESH_STALE, "1").strip().lower() not in ("0", "false", "no", "off")


def env_cap() -> int:
    try:
        return max(0, int(os.getenv(ENV_CAP, str(DEFAULT_CAP)).strip() or DEFAULT_CAP))
    except ValueError:
        return DEFAULT_CAP


def daily_cap() -> int:
    """하루 호출 상한 = `ONEBOUND_DAILY_CAP`과 **키가 실제로 허용하는 수**(응답 `api_info` max) 중 작은 쪽.
    오너 실측(2026-10-07): CAP 60 > 키 max 10이라 우리 가드가 먼저 막지 못하고 온바운드 4013(已超量)을 받았다."""
    lim = api_limits()
    learned, exp = lim.get("max"), str(lim.get("expires") or "")
    cap = env_cap()
    if exp and exp < _cst_day():                             # 배운 max의 키가 만료됐으면(체험 → 유료 키) 쓰지 않는다
        return cap
    return min(cap, int(learned)) if isinstance(learned, int) and learned > 0 else cap


# ── 4013(已超量) — 키 일일 한도 소진 ────────────────────────────────────────────
QUOTA_KIND = "provider_quota"
QUOTA_LINE = "상품정보 서비스 일일 한도 — 내일 다시 또는 충전 후"
_LIMITS = "onebound:api_limits"           # 응답 api_info에서 배운 {max, today, expires, at}
_QUOTA = "onebound:quota_block:"          # + 베이징 날짜 → {code, reason, at}


def _cst_day(now=None) -> str:
    return (now or datetime.now(timezone.utc)).astimezone(_CST).strftime("%Y-%m-%d")


def api_limits() -> Dict[str, Any]:
    from src.db import image_translate_queue_pg as st
    return st.state_get(_LIMITS) or {}


def _learn_limits(raw: Any) -> None:
    """응답마다 `api_info`(today/max/expires)를 기억 — 다음 호출부터 상한이 키의 max로 내려간다."""
    if not isinstance(raw, dict) or not raw.get("api_info"):
        return
    info = parse_api_info(raw.get("api_info"))
    if info.get("max") is None:
        return
    from src.db import image_translate_queue_pg as st
    st.state_set(_LIMITS, {"max": info["max"], "today": info.get("today"), "expires": info.get("expires") or "",
                           "at": datetime.now(timezone.utc).isoformat()})
    if env_cap() > info["max"]:
        logger.warning("[onebound] ONEBOUND_DAILY_CAP=%s > 키 일일 max %s — 상한을 %s로 낮춰 씀", env_cap(), info["max"], info["max"])


def is_quota_error(code: str, reason: str) -> bool:
    return str(code or "") == "4013" or "已超量" in str(reason or "")


def quota_block(now=None) -> Dict[str, Any]:
    """오늘(베이징 날짜) 4013을 이미 받았나 — 받았으면 그 기록. 자동 경로는 이걸 보면 **부르지 않는다**(건당 과금)."""
    from src.db import image_translate_queue_pg as st
    return st.state_get(_QUOTA + _cst_day(now)) or {}


def _set_quota_block(code: str, reason: str) -> None:
    from src.db import image_translate_queue_pg as st
    st.state_set(_QUOTA + _cst_day(), {"code": code, "reason": reason[:200], "at": datetime.now(timezone.utc).isoformat()})


def _clear_quota_block() -> None:
    from src.db import image_translate_queue_pg as st
    st.state_set(_QUOTA + _cst_day(), {})


def _day_key(now=None) -> str:
    """하루 호출 수 키 — **베이징 날짜**(Z3-C). 온바운드 한도는 베이징 자정에 리셋되는데 KST로 세면
    KST 00:00~01:00 호출이 우리 쪽에선 「새 날」, 온바운드에선 「어제」라 어긋났다."""
    return "onebound_calls:" + _cst_day(now)


def used_today() -> int:
    from src.db import option_translate_queue_pg as q
    return q.day_count(_day_key())


def _take(manual: bool = False) -> bool:
    """한도 한 칸. 사람이 누른 「새로 받기」는 env 상한으로 — 충전·키 교체 뒤 새 max를 배울 길을 막지 않는다."""
    from src.db import option_translate_queue_pg as q
    granted, _n = q.take_n(_day_key(), env_cap() if manual else daily_cap(), 1)
    return granted >= 1


def parse_api_info(s: Any) -> Dict[str, Any]:
    """`"today:1 max:10 all[1=1+0+0];expires:2026-10-08"` → `{today: 1, max: 10, expires: "2026-10-08"}`.
    `today: max:10`처럼 오늘 수가 비면 today=None. 못 읽어도 호출은 계속."""
    s = str(s or "")
    t = re.search(r"today\s*:\s*(\d+)", s)
    m = re.search(r"max\s*:\s*(\d+)", s)
    e = re.search(r"expires\s*:\s*(\d{4}-\d{2}-\d{2})", s)
    return {"today": int(t.group(1)) if t else None, "max": int(m.group(1)) if m else None,
            "expires": e.group(1) if e else "", "raw": s[:120]}


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
    """「//…」 · 「http://…」 → https(오너 실측: prop_img·props_img가 http://로 오는 경우 있음)."""
    u = str(u or "").strip()
    if u.startswith("//"):
        return "https:" + u
    return "https://" + u[7:] if u.lower().startswith("http://") else u


def item_id_mismatch(raw: Any, num_iid: str) -> str:
    """응답 item.num_iid ≠ 요청 상품번호면 사유(캐시 오염 방어) — 같으면 빈 문자열."""
    got = str((((raw or {}).get("item") or {}) if isinstance(raw, dict) else {}).get("num_iid") or "").strip()
    want = str(num_iid or "").strip()
    if not got:
        return f"온바운드 응답에 상품번호 없음(요청 {want}) — 캐시 오염 의심, 쓰지 않음"
    if got != want:
        return f"온바운드 응답 상품번호 불일치(요청 {want} ≠ 응답 {got}) — 캐시 오염 의심, 쓰지 않음"
    return ""


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


UNLISTED = "미기재"


def _listed(v: Any):
    """배송비·무게 칸 — null·""·0·숫자 아님 → 「미기재」, 그 밖엔 숫자(float)."""
    f = _float(v)
    return UNLISTED if (f is None or f == 0) else f


def _brand(v: Any) -> Optional[str]:
    b = str(v or "").strip()
    if not b or b.lower() in ("other", "others", "none", "null") or b in ("其他", "其它", "无", "无品牌", "other/其他", "other/其它"):
        return None
    return None if re.fullmatch(r"(?i)other\s*/\s*其[他它]", b) else b


def _dedup(urls) -> List[str]:
    out, seen = [], set()
    for u in urls:
        u = _https(u)
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def stale_cache(raw: Any, now=None) -> bool:
    """응답이 캐시(cache=1)이고 data_update가 24시간 넘었나 — 자동 경로의 `cache=no` 재호출 조건."""
    if not isinstance(raw, dict) or not _truthy(raw.get("cache")):
        return False
    return _stale(str(raw.get("data_update") or ((raw.get("item") or {}).get("data_update") if isinstance(raw.get("item"), dict) else "") or ""), now)


def _stale(data_update: str, now=None) -> bool:
    """`data_update`가 하루 넘게 지났나. 못 읽으면 True(기준 날짜를 보이는 편이 안전)."""
    s = str(data_update or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            t = datetime.strptime(s[:19], fmt).replace(tzinfo=_CST)
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
    item = (raw or {}).get("item") if isinstance((raw or {}).get("item"), dict) else {}
    notes: List[str] = []
    imgs = _dedup([item.get("pic_url")] + [x.get("url") for x in (item.get("item_imgs") or []) if isinstance(x, dict)])
    desc = [u for u in _dedup(u for u in (item.get("desc_img") or []) if isinstance(u, str)) if not _PIXEL.search(u)]
    if not desc:                                   # desc_img가 비면 desc(html)의 <img src>에서(o0b.cn 픽셀 제외)
        found = re.findall(r"""<img[^>]+src\s*=\s*["']([^"']+)["']""", str(item.get("desc") or ""), re.I)
        desc = [u for u in _dedup(found) if not _PIXEL.search(u)]
        if desc:
            notes.append(f"desc_img 비어 desc(html)에서 상세 사진 {len(desc)}장")
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
    # 옵션값 사진 — 실측(오너 2026-10-05, 652874751412): prop_imgs.prop_img[] = [{"properties": "pid:vid", "url": …}],
    #   props_img = {"pid:vid": url}. 둘 다 http://로 올 수 있어 https 보정. prop_img가 우선, props_img는 빈 자리만 채운다.
    # 실측(667810641388): prop_imgs · props_imgs(복수형) 둘 다 올 수 있다 — prop_imgs 우선, 없으면 props_imgs.
    _pi = item.get("prop_imgs") if isinstance(item.get("prop_imgs"), dict) and (item["prop_imgs"].get("prop_img")) else item.get("props_imgs")
    pimg = _pi.get("prop_img") if isinstance(_pi, dict) else None
    pairs = [(x.get("properties"), x.get("url")) for x in (pimg or []) if isinstance(x, dict)]
    if isinstance(item.get("props_img"), dict):
        pairs += list(item["props_img"].items())
    for pv, url in pairs:
        pv = str(pv or "").strip()
        if pv in pv_name and url and pv_name[pv][1] not in opt_imgs:
            opt_imgs[pv_name[pv][1]] = _https(url)
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
        "video_url": (_https(video.get("url")) or None) if isinstance(video, dict) else None,
        "origin_city": str(item.get("location") or ""), "is_tmall": _truthy(item.get("tmall")),
        "shop_name": str(seller.get("shop_name") or item.get("nick") or ""), "stock_total": _int(item.get("num")),
        # 타입 관용(실측: total_sold 1호 int 0 · 2호 str "6") — 판매수는 참고만(믿지 않음)
        "total_sold": _int(item.get("total_sold")), "sales": _int(item.get("sales")),
        # 배송비·무게: null·""·0은 「미기재」 — Z5 배송비 계산에 0으로 넣지 않는다(부피·규격표 추정 경로 그대로)
        **{k: _listed(item.get(k)) for k in ("post_fee", "express_fee", "ems_fee", "freight", "item_weight")},
        # 브랜드: other/其他·빈 값은 브랜드 없음(None) — Y6 IP 게이트·상품명에 넘기지 않는다(병합 페이로드엔 원래 안 실음)
        "brand": _brand(item.get("brand")),
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


def call(num_iid: str, *, refresh: bool = False, no_cache: bool = False, transport=None) -> Dict[str, Any]:
    """`{ok, kind, why, raw, ms, bytes, reused}`. 24시간 안 보관본이 있으면 재사용(refresh=True면 재호출).
    `no_cache`=True면 `cache=no`(온바운드 캐시 우회) — 「새로 받기」·자동 경로의 하루 넘은 캐시 재호출."""
    iid = str(num_iid or "").strip()
    if not iid:
        return {"ok": False, "kind": "provider_fail", "why": "상품번호 해석 실패", "raw": None, "ms": 0, "bytes": 0}
    rec = stored(iid)
    if rec.get("raw") and not (refresh or no_cache) and _fresh(rec) and not item_id_mismatch(rec["raw"], iid):
        return {"ok": True, "kind": "ok", "why": "", "raw": rec["raw"], "ms": 0, "bytes": int(rec.get("bytes") or 0),
                "reused": True, "at": rec.get("at")}
    miss = keys_missing()
    if miss:
        return {"ok": False, "kind": "provider_fail", "why": "공급자 키 미설정 — " + " · ".join(miss), "raw": None,
                "ms": 0, "bytes": 0}
    # 오늘 이미 4013(키 한도 소진)을 받았으면 **부르지 않는다** — 자동 재시도·다른 상품 담기가 건마다 과금되지 않게.
    #   「새로 받기」(refresh, 사람이 누름)만 한 번 시도할 수 있다(충전 뒤 확인용) — 성공하면 막음을 푼다.
    blk = quota_block()
    if blk.get("code") and not refresh:
        return {"ok": False, "kind": QUOTA_KIND, "why": f"{QUOTA_LINE} (온바운드 {blk['code']}: {blk.get('reason', '')[:80]})",
                "raw": None, "ms": 0, "bytes": 0}
    if not _take(manual=refresh):
        return {"ok": False, "kind": "provider_cap",
                "why": f"온바운드 일일 한도 — 오늘 {daily_cap()}회 다 씀(ONEBOUND_DAILY_CAP), 내일 다시", "raw": None,
                "ms": 0, "bytes": 0}
    params = {"key": os.getenv(ENV_KEY, "").strip(), "secret": os.getenv(ENV_SECRET, "").strip(),
              "num_iid": iid, "is_promotion": "1", "lang": "zh-CN"}
    if no_cache:
        params["cache"] = "no"
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
    logger.info("[onebound] num_iid=%s%s HTTP %s · error_code=%s · cache=%s · execution_time=%s · %d바이트 · %dms",
                iid, " (cache=no)" if no_cache else "", status, code or "—", (raw or {}).get("cache") if isinstance(raw, dict) else "—",
                (raw or {}).get("execution_time") if isinstance(raw, dict) else "—", nbytes, ms)
    if not isinstance(raw, dict):
        return {"ok": False, "kind": "provider_fail", "why": f"온바운드 HTTP {status} · JSON 아닌 응답({nbytes}바이트)",
                "raw": None, "ms": ms, "bytes": nbytes}
    _learn_limits(raw)
    if code != "0000" or not isinstance(raw.get("item"), dict):
        said = str(raw.get("reason") or raw.get("error") or "").strip()            # 원문 그대로(번역 안 함)
        if is_quota_error(code, said):
            _set_quota_block(code or "4013", said)
            logger.warning("[onebound] num_iid=%s 키 일일 한도 소진(%s %s) — 오늘은 더 부르지 않음", iid, code, said[:60])
            return {"ok": False, "kind": QUOTA_KIND, "why": f"{QUOTA_LINE} (온바운드 {code or '4013'}: {said[:80]})",
                    "raw": raw, "ms": ms, "bytes": nbytes}
        return {"ok": False, "kind": "provider_fail", "why": f"온바운드 {code or '응답 코드 없음'}" + (f": {said[:160]}" if said else ""),
                "raw": raw, "ms": ms, "bytes": nbytes}
    bad = item_id_mismatch(raw, iid)                     # 다른 상품 응답은 보관도 안 한다
    if bad:
        logger.warning("[onebound] %s", bad)
        return {"ok": False, "kind": "provider_fail", "why": bad, "raw": raw, "ms": ms, "bytes": nbytes}
    _store(iid, raw, nbytes, ms)
    if refresh and quota_block().get("code"):
        _clear_quota_block()                                 # 충전 뒤 「새로 받기」가 성공 — 오늘 막음을 푼다
        try:                                                 # Z3-C: 막음이 풀린 직후 이월 대기를 곧바로 비운다
            from src.services import onebound_carry as _carry
            _carry.kick()
        except Exception as exc:                             # noqa: BLE001
            logger.warning("[onebound] 이월 대기 시작 실패: %s", exc)
    return {"ok": True, "kind": "ok", "why": "", "raw": raw, "ms": ms, "bytes": nbytes, "reused": False}


def fetch_detail(num_iid: str, *, refresh: bool = False, transport=None) -> Dict[str, Any]:
    """`taobao_mtop.fetch`와 같은 모양 — `{state: ok|manual, kind, reason, payload, raw, ms, bytes, reused}`."""
    c = call(num_iid, refresh=refresh, no_cache=refresh, transport=transport)
    bypassed = bool(refresh)
    # 자동 경로: 새로 받은 응답이 캐시(cache=1)이고 data_update가 24시간 넘었으면 cache=no로 1회만 다시(한도 1회로 셈).
    # `ONEBOUND_REFRESH_STALE=0`이면 재호출 없이 받은 캐시 값을 쓴다(카드에 「가격 기준 {data_update}」).
    if c["ok"] and not c.get("reused") and not refresh and stale_cache(c["raw"]) and refresh_stale():
        c2 = call(num_iid, no_cache=True, transport=transport)
        logger.info("[onebound] num_iid=%s 하루 넘은 캐시 → cache=no 재호출 %s", num_iid, "성공" if c2["ok"] else c2["why"])
        if c2["ok"]:
            c2["bytes"] = int(c2.get("bytes") or 0) + int(c.get("bytes") or 0)
            c2["ms"] = int(c2.get("ms") or 0) + int(c.get("ms") or 0)
            c, bypassed = c2, True
    base = {"raw": c.get("raw"), "ms": c.get("ms", 0), "bytes": c.get("bytes", 0), "reused": bool(c.get("reused")),
            "bypassed": bypassed}
    if not c["ok"]:
        return {"state": "manual", "kind": c["kind"], "reason": c["why"], "payload": None, **base}
    payload = normalize(c["raw"])
    if not (payload["title"] and payload["images"]):
        return {"state": "manual", "kind": "provider_fail", "reason": "온바운드 응답에 제목·사진이 비었어요", "payload": None, **base}
    return {"state": "ok", "kind": "ok", "reason": "", "payload": payload, **base}

"""Z3-B(오너 2026-10-05) — 타오바오 상세를 **외부 공급자 API**로. 익명 mtop이 로그인 요구로 막혀서(IP 무관) 붙인다.

`TAOBAO_DETAIL_PROVIDER` = mtop(기본) | onebound
  onebound: `ONEBOUND_KEY` · `ONEBOUND_SECRET`(값은 로그·화면에 안 남김) · `ONEBOUND_DAILY_CAP`(기본 100 — 넘으면 「일일 한도」 보류)
  실패하면 그 건은 (c) 수동 카드로 — mtop을 다시 부르지 않는다.

`fetch_detail(item_id)`의 `payload`는 `taobao_mtop.enrich_payload`와 **같은 키**(title·images·options·skus·price·currency·
detail_images·source_path) → 뒤 파이프라인(`extension_api.apply_enrich`)은 그대로.

★ 필드명 추측 금지(오너 지시). 이 컨테이너는 onebound 문서(open.onebound.cn)에 못 나간다(egress 차단).
  여기 쓰는 키는 **웹 검색 결과로 확인된 것만**이다 — 출처는 `FIELDS_SOURCE`.
  `tests/fixtures/providers/onebound_item_get.json`은 그 키로 만든 **재구성** 표본이다. 첫 실응답은 진단 화면이 저장하고
  내려받기 링크를 준다 → 그 파일로 교체하고 파서 테스트를 다시 돌린다(실응답 모양이 다르면 테스트가 먼저 깨진다).
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

ENDPOINT = "https://api-gw.onebound.cn/taobao/item_get/"
ENV_KEY, ENV_SECRET, ENV_CAP = "ONEBOUND_KEY", "ONEBOUND_SECRET", "ONEBOUND_DAILY_CAP"
FIELDS_SOURCE = ("웹 검색 결과(2026-10-05): 요청 key·secret·num_iid·is_promotion / 응답 error_code(\"0000\"=성공)·"
                 "item.num_iid·title·price·orginal_price·pic_url·item_imgs[].url·desc_img[]·props_list(\"pid:vid\":\"축:값\")·"
                 "skus.sku[](price·orginal_price·quantity·sku_id·properties·properties_name"
                 "=\"pid:vid:축:값;…\") — 문서 원문 미확인, 실응답으로 교체 전")
BILLING_UNIT = "상품 1건 = item_get 호출 1회(이 서버 카운터 기준 — 실제 단가·잔여는 onebound 계정 화면)"
_KST = timezone(timedelta(hours=9))
_SAMPLE = "onebound:sample_item_get"


def provider() -> str:
    v = os.getenv("TAOBAO_DETAIL_PROVIDER", "mtop").strip().lower()
    return v if v in ("mtop", "onebound") else "mtop"


def keys_missing() -> List[str]:
    return [k for k in (ENV_KEY, ENV_SECRET) if not os.getenv(k, "").strip()]


def daily_cap() -> int:
    try:
        return max(0, int(os.getenv(ENV_CAP, "100").strip() or 100))
    except ValueError:
        return 100


def status() -> Dict[str, Any]:
    miss = keys_missing()
    if miss:
        return {"state": "미설정", "line": "키 미설정 — " + " · ".join(miss)}
    return {"state": "ready", "line": f"키 설정됨 · 일일 한도 {daily_cap()}건(ONEBOUND_DAILY_CAP) · 오늘 {used_today()}건 사용"}


def startup_check() -> str:
    """부팅 1줄 — 공급자가 onebound인데 키가 없으면 경고(그 건들은 「키 미설정」으로 (c) 수동)."""
    if provider() != "onebound":
        return ""
    miss = keys_missing()
    if miss:
        msg = "Z3-B 공급자: TAOBAO_DETAIL_PROVIDER=onebound인데 키 미설정(" + ", ".join(miss) + ") — 그 건은 수동 카드로"
        logger.warning(msg)
        return msg
    msg = f"Z3-B 공급자: onebound · 일일 한도 {daily_cap()}건"
    logger.info(msg)
    return msg


def _day_key(now=None) -> str:
    return "onebound_calls:" + (now or datetime.now(timezone.utc)).astimezone(_KST).strftime("%Y-%m-%d")


def used_today() -> int:
    from src.db import option_translate_queue_pg as q
    return q.day_count(_day_key())


def _take() -> bool:
    from src.db import option_translate_queue_pg as q
    granted, _n = q.take_n(_day_key(), daily_cap(), 1)
    return granted >= 1


def mask_raw(raw: Any) -> Any:
    """진단 화면용 — 응답에 키·시크릿 비슷한 값이 섞여 오면 글자 수로 가린다."""
    secrets = [v for v in (os.getenv(ENV_KEY, "").strip(), os.getenv(ENV_SECRET, "").strip()) if v]

    def walk(x):
        if isinstance(x, dict):
            return {k: (f"<{len(str(v))}자 가림>" if re.search(r"key|secret|token", str(k), re.I) and isinstance(v, str)
                        else walk(v)) for k, v in x.items()}
        if isinstance(x, list):
            return [walk(v) for v in x]
        if isinstance(x, str):
            for s in secrets:
                x = x.replace(s, f"<{len(s)}자 가림>")
        return x
    return walk(raw)


def _abs(u: Any) -> str:
    u = str(u or "").strip()
    return "https:" + u if u.startswith("//") else u


def _num(v: Any):
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _sku_list(item: dict) -> list:
    """skus는 `{"sku": [...]}`(검색 결과의 모양). 다른 모양이면 빈 목록 + parse_notes에 남긴다(추측해서 읽지 않음)."""
    sk = item.get("skus")
    if isinstance(sk, dict) and isinstance(sk.get("sku"), list):
        return [x for x in sk["sku"] if isinstance(x, dict)]
    return []


def _pairs(properties_name: str) -> list:
    """`"1627207:101620863:颜色分类:米色;122216343:3285954:参考身高:130cm"` → [("颜色分类","米色"), ("参考身高","130cm")]."""
    out = []
    for part in str(properties_name or "").split(";"):
        bits = part.split(":", 3)
        if len(bits) == 4 and bits[2]:
            out.append((bits[2].strip(), bits[3].strip()))
    return out


def normalize(raw: dict) -> Dict[str, Any]:
    """onebound item_get 응답 → `enrich_payload` 같은 키 + `parse_notes`(못 읽은 것). 가격은 float."""
    item = (raw or {}).get("item") or {}
    notes = []
    imgs, seen = [], set()
    for u in [item.get("pic_url")] + [x.get("url") if isinstance(x, dict) else None for x in (item.get("item_imgs") or [])]:
        u = _abs(u)
        if u and u not in seen:
            seen.add(u)
            imgs.append(u)
    axes: Dict[str, List[str]] = {}
    skus = []
    sku_rows = _sku_list(item)
    if item.get("skus") and not sku_rows:
        notes.append("skus 모양이 {sku:[…]}가 아님 — SKU 안 읽음(실응답 확인 필요)")
    for k in sku_rows:
        pairs = _pairs(k.get("properties_name"))
        for name, val in pairs:
            vals = axes.setdefault(name, [])
            if val not in vals:
                vals.append(val)
        p = _num(k.get("price"))
        q = k.get("quantity")
        skus.append({"spec": [v for _n, v in pairs], "price": "" if p is None else p,
                     "stock": int(q) if str(q or "").strip().isdigit() else None, "sku_id": str(k.get("sku_id") or "")})
    if not axes and isinstance(item.get("props_list"), dict):        # SKU가 없을 때 축은 props_list("축:값")에서만
        for v in item["props_list"].values():
            name, _, val = str(v).partition(":")
            if name and val:
                vals = axes.setdefault(name.strip(), [])
                if val.strip() not in vals:
                    vals.append(val.strip())
    price = _num(item.get("price"))
    if price is None:
        notes.append("item.price 숫자 아님")
    return {"title": str(item.get("title") or ""), "images": imgs,
            "options": [{"name": n, "values": v} for n, v in axes.items()], "skus": skus,
            "price": price if price is not None else "", "currency": "CNY",
            "detail_images": [_abs(u) for u in (item.get("desc_img") or []) if isinstance(u, str) and u],
            "source_path": "onebound", "parse_notes": notes}


def call(item_id: str, *, transport=None) -> Dict[str, Any]:
    """item_get 한 번 — `{ok, raw, ms, size, why, kind}`. 한도·키는 여기서 막는다(호출 전)."""
    iid = str(item_id or "").strip()
    miss = keys_missing()
    if miss:
        return {"ok": False, "kind": "provider_fail", "why": "키 미설정 — " + " · ".join(miss), "raw": None, "ms": 0, "size": 0}
    if not _take():
        return {"ok": False, "kind": "provider_cap",
                "why": f"일일 한도 — 오늘 {daily_cap()}건 다 씀(ONEBOUND_DAILY_CAP), 내일 다시", "raw": None, "ms": 0, "size": 0}
    params = {"key": os.getenv(ENV_KEY, "").strip(), "secret": os.getenv(ENV_SECRET, "").strip(),
              "num_iid": iid, "is_promotion": "1"}
    t0 = time.monotonic()
    try:
        if transport is not None:
            status, text = transport(ENDPOINT, params)
        else:
            import requests
            r = requests.get(ENDPOINT, params=params, timeout=25)
            status, text = r.status_code, r.text or ""
    except Exception as exc:                                    # noqa: BLE001
        ms = int((time.monotonic() - t0) * 1000)
        logger.info("[onebound] item_id=%s 실패 %s · %dms", iid, type(exc).__name__, ms)
        return {"ok": False, "kind": "provider_fail", "why": f"요청 실패 {type(exc).__name__}", "raw": None, "ms": ms, "size": 0}
    ms, size = int((time.monotonic() - t0) * 1000), len(str(text).encode("utf-8"))
    logger.info("[onebound] item_id=%s HTTP %s · 응답 %d바이트 · %dms", iid, status, size, ms)
    try:
        raw = json.loads(text)
    except Exception:
        return {"ok": False, "kind": "provider_fail", "why": f"HTTP {status} · JSON 아닌 응답({size}바이트)", "raw": None,
                "ms": ms, "size": size}
    code = str((raw or {}).get("error_code") or "")
    if code != "0000" or not isinstance(raw.get("item"), dict):
        why = str(raw.get("reason") or raw.get("error") or "")[:120]
        return {"ok": False, "kind": "provider_fail", "why": f"onebound error_code {code or '없음'}" + (f" — {why}" if why else ""),
                "raw": raw, "ms": ms, "size": size}
    return {"ok": True, "kind": "ok", "why": "", "raw": raw, "ms": ms, "size": size}


def save_sample(raw: dict, item_id: str = "") -> bool:
    """첫 실응답 1건 — 재구성 픽스처를 이걸로 교체(키는 가려서 저장)."""
    from src.db import image_translate_queue_pg as st
    if not raw or (st.state_get(_SAMPLE) or {}).get("raw"):
        return False
    st.state_set(_SAMPLE, {"raw": mask_raw(raw), "item_id": item_id, "at": datetime.now(timezone.utc).isoformat()})
    return True


def sample() -> Dict[str, Any]:
    from src.db import image_translate_queue_pg as st
    return st.state_get(_SAMPLE) or {}


def fetch_detail(item_id: str, *, transport=None) -> Dict[str, Any]:
    """`taobao_mtop.fetch`와 같은 모양 — `{state: ok|manual, kind, reason, payload, raw, ms, size}`."""
    c = call(item_id, transport=transport)
    if not c["ok"]:
        return {"state": "manual", "kind": c["kind"], "reason": c["why"], "payload": None, "raw": c.get("raw"),
                "ms": c["ms"], "size": c["size"]}
    save_sample(c["raw"], item_id)
    payload = normalize(c["raw"])
    if not (payload["title"] and payload["images"]):
        return {"state": "manual", "kind": "provider_fail", "reason": "onebound 응답에 제목·사진이 비었어요",
                "payload": None, "raw": c["raw"], "ms": c["ms"], "size": c["size"]}
    return {"state": "ok", "kind": "ok", "reason": "", "payload": payload, "raw": c["raw"], "ms": c["ms"], "size": c["size"]}

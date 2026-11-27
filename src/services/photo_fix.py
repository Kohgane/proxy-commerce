"""오너 11-26 저녁 ① — 오너 탭 줄이기: 「다시 가져오기 → 진단 주소 → 사진 다시 보내기」(상품마다 세 번)를 한 자리로.

· `measure(urls)` — 사진 긴 변을 실제로 잰다(머리만 · 예산 안에서). 「전부 1000px 넘음」은 **잰 장만** 말한다(지어내기 0).
· `refetch_line(ex)` — 「다시 가져오기」가 끝난 카드에 결과 한 줄(사진 전→후 장 · 잰 크기 · 옵션별 가격 수).
· `resend_targets(ex)` — 이미 스스에 올라간 상품이고, 올린 **뒤에** 사진이 바뀌었고, 그 뒤로 다시 보내지 않았으면 그 등록 기록.
· `judge(ex)` — 목록 맨 위 「사진 고칠 상품 N건」 재료: ready(새 사진 준비됨 — 다시 보내기만 남음) · small(올라간 사진이 작은 판 —
  다시 가져오기부터). 등록 기록 + 쓸 만한 사진 판정(주소 크기 토큰 · 다시 가져오기 때 잰 크기)만 본다 — 마켓에 묻지 않는다.

마켓에 보내는 건 여전히 오너 탭(`/collect/<id>/naver-resend-photos` · 두 번 눌러야 보냄)이다.
"""
from __future__ import annotations

import re
import time
from typing import Callable, Dict, List, Optional
from urllib.parse import urlparse

#: 목록이 끄는 extra 칸(나머지 extra_json은 안 끈다)
KEYS = ["uploaded", "amazon_refetch", "images", "sku_fill"]

BIG = 1000          # 「전부 1000px 넘음」 문턱(오너 예시) — 잰 장 기준
SMALL = 500         # 사전검증·사진 다시 보내기와 같은 잣대(coupang_image_check.MIN_LONG_SIDE)

# 주소에 크기가 박혀 있는 작은 판(네트워크 0) — 잰 근거가 있는 꼴만:
#   알리 `…jpg_480x480q75.jpg_.avif`(실측 FULLSIZE1126: 480 썸네일) · 테무 kwcdn `imageView2/…/w/180`
_ALI_TOKEN_RE = re.compile(r"\.(?:jpe?g|png|webp)_(\d{2,4})x(\d{2,4})(?:q\d+)?\.", re.I)
_KW_W_RE = re.compile(r"(?:^|[/&?])w/(\d{2,4})(?:[/&]|$)")


def _ali_like(host: str) -> bool:
    return host.endswith("alicdn.com") or host.endswith("aliexpress-media.com")


def url_small(url: str) -> Optional[bool]:
    """주소만 보고 작은 판인가 — True(작음) · False(쓸 만함) · None(주소로는 모름)."""
    u = str(url or "")
    host = (urlparse(u).hostname or "").lower()
    if not host:
        return None
    if "amazon" in host:
        from src.collectors.amazon_pdp import usable_photo
        return not usable_photo(u)
    if _ali_like(host):
        m = _ALI_TOKEN_RE.search(u)
        if not m:
            return None
        return max(int(m.group(1)), int(m.group(2))) < SMALL
    if host == "img.kwcdn.com":
        q = urlparse(u).query or ""
        if "imageView2" not in q and "imageMogr2" not in q:
            return None
        m = _KW_W_RE.search("/" + q)
        return (int(m.group(1)) < SMALL) if m else None
    return None


def measure(urls, *, budget: float = 20.0, limit: int = 12,
            size_of: Optional[Callable] = None, clock: Callable = time.time) -> Dict:
    """사진 긴 변을 실제로 잰다(머리만). `{n, measured, min, max, under}` — 못 잰 장은 `failed`에 센다."""
    if size_of is None:
        from src.services.coupang_image_check import size_of
    imgs = [u for u in (urls or []) if isinstance(u, str) and u][:limit]
    t0, sides, failed = clock(), [], 0
    for u in imgs:
        if clock() - t0 > budget:
            break
        try:
            ls = int((size_of(u) or {}).get("long_side") or 0)
        except Exception:                                      # noqa: BLE001 — 못 재면 센다(막지 않음)
            ls = 0
        if ls:
            sides.append(ls)
        else:
            failed += 1
    out = {"n": len(imgs), "measured": len(sides), "failed": failed}
    if sides:
        out.update(min=min(sides), max=max(sides), under=sum(1 for s in sides if s < SMALL))
    return out


def _size_phrase(sz: Dict) -> str:
    m = int(sz.get("measured") or 0)
    if not m:
        return "크기는 못 쟀어요" if sz.get("n") else ""
    lo, hi = int(sz.get("min") or 0), int(sz.get("max") or 0)
    if lo >= BIG:
        head = f"잰 {m}장 전부 긴 변 {BIG}px 넘어요"
    elif lo >= SMALL:
        head = f"잰 {m}장 전부 긴 변 {SMALL}px 넘어요(가장 작은 장 {lo}px)"
    elif hi < SMALL:
        head = f"잰 {m}장 전부 {SMALL}px 미만(가장 큰 장 {hi}px)"
    else:
        head = f"잰 {m}장 중 {int(sz.get('under') or 0)}장이 {SMALL}px 미만(가장 작은 장 {lo}px)"
    if sz.get("failed"):
        head += f" · {int(sz['failed'])}장은 못 잼"
    return head


def refetch_line(ex: Dict) -> str:
    """「다시 가져오기」 결과 한 줄 — 기록이 없으면 빈 문자열."""
    rec = (ex or {}).get("amazon_refetch")
    if not isinstance(rec, dict) or not rec.get("at"):
        return ""
    if not rec.get("ok"):
        return "다시 가져오지 못했어요 — " + str(rec.get("reason") or "사유 없음")
    b, a = rec.get("before") or {}, rec.get("after") or {}
    bits = [f"사진 {int(b.get('images') or 0)}→{int(a.get('images') or 0)}장"]
    sp = _size_phrase(a.get("sizes") or {})
    if sp:
        bits.append(sp)
    sf = (ex or {}).get("sku_fill") if isinstance((ex or {}).get("sku_fill"), dict) else {}
    if sf.get("state") == "done":
        bits.append(f"옵션가 {int(sf.get('priced') or 0)}개" + (f"(가격 없음 {int(sf['missing'])}개)" if sf.get("missing") else ""))
    elif sf.get("state") == "pending":
        bits.append("옵션별 가격 읽는 중")
    return " · ".join(bits)


def taobao_line(ex: Dict, before_images: Optional[int] = None) -> str:
    """오너 11-27 ①: 타오바오 서버 다시 가져오기(`auto_enrich`) 결과 한 줄 — 지금 행에 들어 있는 것만 센다."""
    ae = (ex or {}).get("auto_enrich")
    if not isinstance(ae, dict) or not ae.get("at"):
        return ""
    if ae.get("state") != "done":
        return "다시 가져오지 못했어요 — " + str(ae.get("reason") or ae.get("state") or "사유 없음")
    imgs = len([u for u in (ex.get("images") or []) if isinstance(u, str) and u])
    opts = sum(len(o.get("values") or []) for o in (ex.get("options") or []) if isinstance(o, dict))
    skus = [k for k in (ex.get("skus") or []) if isinstance(k, dict) and str(k.get("price") or "").strip()]
    head = f"사진 {before_images}→{imgs}장" if before_images is not None else f"사진 {imgs}장"
    return f"{head} · 옵션 값 {opts}개 · 옵션가 {len(skus)}개"


def _ss_records(ex: Dict) -> List[Dict]:
    from src.seller_console import listing_status as MS
    out = []
    for r in MS.records(ex or {}):
        if r["market"].startswith("smartstore") and r.get("product_id"):
            out.append(r)
    return out


def _resent_at(ex: Dict, market: str) -> str:
    for u in (ex or {}).get("uploaded") or []:
        if isinstance(u, dict) and u.get("market") == market and isinstance(u.get("photo_resent"), dict):
            return str(u["photo_resent"].get("at") or "")
    return ""


def resend_targets(ex: Dict) -> List[Dict]:
    """스스에 올린 **뒤에** 다시 가져오기로 사진이 바뀌었고, 그 뒤로 다시 보내지 않은 등록 기록."""
    rec = (ex or {}).get("amazon_refetch")
    if not isinstance(rec, dict) or not rec.get("ok") or not rec.get("at"):
        return []
    a, b = rec.get("after") or {}, rec.get("before") or {}
    if not int(a.get("images") or 0):
        return []
    changed = (int(a.get("usable") or 0) > int(b.get("usable") or 0)) or (int(a.get("images") or 0) != int(b.get("images") or 0))
    sz = a.get("sizes") or {}
    if not changed and not (sz.get("measured") and int(sz.get("min") or 0) >= SMALL):
        return []
    if sz.get("measured") and int(sz.get("max") or 0) < SMALL:
        return []                                              # 새로 읽은 것도 전부 작다 — 보내도 흐리다
    if not sz.get("measured") and not int(a.get("usable") or 0):
        return []                                              # 잰 것도 없고 주소로도 쓸 만한 장이 0 — 보내도 흐리다
    at = str(rec["at"])
    out = []
    for r in _ss_records(ex):
        if r.get("at") and r["at"] >= at:
            continue                                           # 다시 가져온 뒤에 올린 등록본 — 이미 새 사진
        if _resent_at(ex, r["market"]) >= at:
            continue                                           # 이미 다시 보냄
        out.append({"market": r["market"], "label": r.get("label") or r.get("chip") or r["market"],
                    "product_id": r["product_id"]})
    return out


def judge(ex: Dict) -> Optional[Dict]:
    """목록 묶음 재료 — None(손댈 것 없음) · {state: ready|small, line, markets}."""
    recs = _ss_records(ex)
    if not recs:
        return None
    tgt = resend_targets(ex)
    if tgt:
        return {"state": "ready", "markets": [t["market"] for t in tgt],
                "line": "새 사진이 준비됐어요 — 스스에 다시 보내기만 남았어요"}
    rec = (ex or {}).get("amazon_refetch") if isinstance((ex or {}).get("amazon_refetch"), dict) else {}
    a = rec.get("after") or {} if rec.get("ok") else {}
    sz = a.get("sizes") or {}
    good = bool(rec.get("ok")) and (int(a.get("usable") or 0) > 0 or (sz.get("measured") and int(sz.get("min") or 0) >= SMALL)) \
        and not (sz.get("measured") and int(sz.get("max") or 0) < SMALL)
    # 손댈 등록본 = 다시 보낸 적 없고, 쓸 만한 사진을 다시 가져온 **뒤에** 올린 것도 아닌 것
    pending = [r for r in recs if not _resent_at(ex, r["market"]) and not (good and str(rec.get("at") or "") <= (r.get("at") or ""))]
    if not pending:
        return None
    again = bool(rec.get("ok")) and any(str(rec.get("at") or "") > (r.get("at") or "") for r in pending)
    tail = "사진을 직접 올린 뒤 스스에 다시 보내요" if again else "다시 가져온 뒤 스스에 다시 보내요"
    if sz.get("measured") and int(sz.get("max") or 0) < SMALL:
        return {"state": "small", "markets": [r["market"] for r in pending],
                "line": f"사진이 전부 {SMALL}px 미만이에요(가장 큰 장 {int(sz['max'])}px) — {tail}"}
    imgs = [u for u in ((ex or {}).get("images") or []) if isinstance(u, str) and u][:10]
    verdicts = [url_small(u) for u in imgs]
    known = [v for v in verdicts if v is not None]
    if imgs and known and len(known) == len(verdicts) and all(known):
        return {"state": "small", "markets": [r["market"] for r in pending],
                "line": f"올라간 사진 {len(imgs)}장이 모두 작은 판이에요 — {tail}"}
    return None


def bundle(rows: List[Dict], extra_of: Callable[[Dict], Dict]) -> Dict:
    """목록 행 → `{n, ready, small, ids}` (마켓에 묻지 않는다)."""
    ids, ready, small = [], 0, 0
    for it in rows or []:
        j = judge(extra_of(it))
        if not j:
            continue
        ids.append(str(it.get("id")))
        if j["state"] == "ready":
            ready += 1
        else:
            small += 1
    return {"n": len(ids), "ready": ready, "small": small, "ids": ids}

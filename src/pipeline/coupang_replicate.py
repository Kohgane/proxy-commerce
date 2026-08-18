"""src/pipeline/coupang_replicate.py — v88-C: 쿠팡 기등록 상품 → 고가브릿지 → 멀티채널 복제 파이프라인 코어.

오너 지시(v88-C): 신규 소싱 아님. 쿠팡 두 계정(고가네 A01381223·우주대행 A01504840) **판매중 상품**을
sourcing_map(ASIN→소싱 URL, LinkLynk/Bluehost 계보)으로 조인 → 소싱 URL을 고가브릿지 **수집 이력**으로
벌크 인입 → 번역·분류·가격까지 자동, **마켓 등록 직전 정지**(등록은 오너 클릭). 이 서버엔 sourcing_map·쿠팡
자격이 없으므로(정직) 라이브 조인/파일럿은 `access_status()`가 막고 **가짜 수치 0**으로 보고한다. 순수 로직은
전량 오프라인 테스트 가능.

불변(오너 금지):
  - 자동 등록 금지(사전검증까지만) · 쿠팡 데이터 무변경(읽기만) · 이미지 2장 초과 금지 · 라쿠텐 서버 크롤 강행 금지
    (차단 리스크 — 분리 보고만) · 별도 우회 경로 발명 금지(수집 5필드·번역 체인·분류는 기존 파이프라인 통과).
  - 가격 = **원가 기준 재계산**(쿠팡 판매가 역산 아님). 공식은 MarginCalculator.reverse_calculate 문서식 재사용:
      판매가 = 총비용 / (1 - 수수료율/100 - 마진율/100).  단 복제는 원가가 이미 랜딩코스트 → 총비용=원가
      (해외직구 국제배송 가산 없음). 채널 수수료: 멀티샵(WC 국내)=3.0(오너 확정), Shopify(글로벌)=env(오너 설정).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

# 재사용: 수집 상품 정규화 키(중복 방지, v42 1-3) — 별 구현 금지.
from src.collectors.product_key import normalize_product_key
# 재사용: 금지어 사전(취급금지 term 필터).
from src.ai.forbidden_terms import check_forbidden_terms

# ── 상수 (오너 확정 사실) ──────────────────────────────────────────────────────
DEFAULT_MARGIN_RATE = 27.4          # 오너 확정 목표 마진율(%).
CHANNEL_FEE_RATES = {                # 채널 판매수수료율(%). 멀티샵만 오너 확정(3%).
    "woocommerce_multishop": 3.0,    # WC 멀티샵(국내, alaz).
    # "shopify_global": env SHOPIFY_FEE_RATE (오너 설정 — 미설정 시 None, 가짜 0 금지).
}
# 쿠팡에서 정리한 금지 카테고리(오너 확정 — 계정 간 동일 적용의 채널 확장판).
FORBIDDEN_CATEGORIES = ["향수", "캔들", "애플", "apple", "casetify"]
# 두 계정(오너 확정) — 계정별 자격은 env(이 서버엔 없음 → access_status가 정직 보고).
COUPANG_ACCOUNTS = {"고가네": "A01381223", "우주대행": "A01504840"}

# sourcing_map 후보 경로(LinkLynk/Bluehost 계보 — 이 서버엔 없을 수 있음).
_SOURCING_MAP_CANDIDATES = [
    os.getenv("SOURCING_MAP_PATH", ""),
    "data/sourcing_map.json",
    "assets/sourcing_map.json",
]


# ── 가격: 원가 기준 재계산 (MarginCalculator 문서식 재사용, 총비용=원가) ─────────
def channel_fee_rate(channel: str) -> Optional[float]:
    """채널 판매수수료율(%). 멀티샵=3.0(확정). shopify_global=env(오너 설정, 미설정=None=정직 미상)."""
    if channel in CHANNEL_FEE_RATES:
        return CHANNEL_FEE_RATES[channel]
    if channel == "shopify_global":
        raw = os.getenv("SHOPIFY_FEE_RATE", "").strip()
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError:
            return None
    return None


def recalc_channel_price(cost_krw: float, channel: str, margin_rate: float = DEFAULT_MARGIN_RATE) -> dict:
    """원가 기준 판매가 재계산 — 판매가 = 원가 / (1 - 수수료율/100 - 마진율/100), 100원 올림.

    쿠팡 판매가 역산 아님(오너 명시). 총비용=원가(랜딩코스트, 국제배송 미가산 — 복제이므로).
    수수료율 미상(shopify env 미설정)이면 가짜 0 대신 ok=False 정직 반환.
    """
    fee = channel_fee_rate(channel)
    if fee is None:
        return {"ok": False, "reason": f"채널 수수료율 미상({channel}) — SHOPIFY_FEE_RATE 등 오너 설정 필요",
                "channel": channel, "cost_krw": cost_krw}
    denom = 1 - (fee / 100.0) - (margin_rate / 100.0)
    if denom <= 0:
        return {"ok": False, "reason": f"마진율({margin_rate}%)+수수료율({fee}%) 합이 100% 초과",
                "channel": channel, "cost_krw": cost_krw}
    optimal = float(cost_krw) / denom
    rounded = int((optimal + 99) // 100) * 100          # 100원 올림(기존 관례)
    return {"ok": True, "channel": channel, "cost_krw": float(cost_krw), "fee_rate": fee,
            "margin_rate": margin_rate, "sale_price_krw": rounded, "optimal_krw": optimal}


# ── 취급금지 필터 (금지어 term + 금지 카테고리 + 주입 blacklist) ─────────────────
def is_forbidden(title: str, category: str = "", blacklist: Optional[Iterable[str]] = None) -> Optional[str]:
    """취급금지면 사유 문자열, 아니면 None. blacklist(쿠팡 85 — 오너 자산)는 주입(하드코딩 금지)."""
    text = f"{title or ''} {category or ''}".lower()
    for kw in FORBIDDEN_CATEGORIES:
        if kw.lower() in text:
            return f"forbidden-category:{kw}"
    for bad in (blacklist or []):
        if bad and str(bad).lower() in text:
            return f"blacklist:{bad}"
    matches = check_forbidden_terms(title or "")
    if matches:
        return f"forbidden-term:{matches[0].term}"
    return None


# ── 소싱 소스 분류 (파일럿 우선순위 + 라쿠텐 분리) ──────────────────────────────
def classify_source(url: str) -> str:
    """소싱 URL → shopify_d2c | amazon | rakuten | other. 라쿠텐=서버 크롤 차단(분리 대상)."""
    u = (url or "").lower()
    if "amazon." in u or "/dp/" in u or "/gp/product/" in u:
        return "amazon"
    if "rakuten.co.jp" in u or "r10s.jp" in u:
        return "rakuten"
    if ".myshopify.com" in u or "/products/" in u or "/products.json" in u:
        return "shopify_d2c"
    return "other"


# ── sourcing_map 로드 (없으면 정직 보고) ────────────────────────────────────────
def load_sourcing_map(path: str = "") -> dict:
    """sourcing_map.json 로드 → {available, path, count, map}. 없으면 available=False(가짜 0)."""
    candidates = [path] + _SOURCING_MAP_CANDIDATES if path else _SOURCING_MAP_CANDIDATES
    for cand in candidates:
        if cand and Path(cand).is_file():
            try:
                data = json.loads(Path(cand).read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
            # 형식 관용: {asin: url} 또는 [{asin, url}] 또는 {asin: {url:...}}.
            m = {}
            if isinstance(data, dict):
                for k, v in data.items():
                    m[str(k).upper()] = v.get("url") if isinstance(v, dict) else str(v)
            elif isinstance(data, list):
                for row in data:
                    if isinstance(row, dict) and row.get("asin"):
                        m[str(row["asin"]).upper()] = row.get("url") or row.get("sourcing_url") or ""
            return {"available": True, "path": cand, "count": len(m), "map": m}
    return {"available": False, "path": None, "count": 0, "map": {},
            "lookup": "LinkLynk/Bluehost 계보 자산 — 오너 액션: 서버에 data/sourcing_map.json 배치 또는 SOURCING_MAP_PATH 설정"}


@dataclass
class JoinRow:
    account: str
    seller_product_id: str
    asin: str
    title: str
    sourcing_url: str
    source: str


@dataclass
class JoinReport:
    on_sale: int = 0                 # 판매중 n
    matched: int = 0                 # 소싱 URL 매칭 m
    unmatched: int = 0               # 미매칭 k
    by_source: dict = field(default_factory=dict)   # 소스별 분포
    rows: list = field(default_factory=list)

    def as_table(self) -> dict:
        return {"판매중": self.on_sale, "매칭": self.matched, "미매칭": self.unmatched,
                "소스분포": self.by_source}


def join_inventory(coupang_items: list, sourcing_map: dict) -> JoinReport:
    """쿠팡 판매중 목록 × sourcing_map(ASIN→URL) 조인 → 수치 보고(1항 수치표).

    coupang_items: [{account, seller_product_id, external_vendor_sku(=ASIN), title}]
    매칭 키 = externalVendorSku(ASIN 계보). 순수 함수(라이브 호출 0) — 입력만으로 결정.
    """
    rep = JoinReport()
    smap = sourcing_map or {}
    for it in coupang_items or []:
        rep.on_sale += 1
        asin = str(it.get("external_vendor_sku") or it.get("asin") or "").upper()
        url = smap.get(asin, "") if asin else ""
        if url:
            src = classify_source(url)
            rep.matched += 1
            rep.by_source[src] = rep.by_source.get(src, 0) + 1
            rep.rows.append(JoinRow(account=str(it.get("account", "")),
                                    seller_product_id=str(it.get("seller_product_id", "")),
                                    asin=asin, title=str(it.get("title", "")),
                                    sourcing_url=url, source=src))
        else:
            rep.unmatched += 1
    return rep


# ── 중복 방지 (멱등) ────────────────────────────────────────────────────────────
def dedup_decision(sourcing_url: str, existing_source_keys: Iterable[str]) -> str:
    """재실행 멱등 — 같은 소스(정규화 키)가 기존에 있으면 'update', 없으면 'new'.

    existing_source_keys = 이미 수집/등록된 소스 URL의 normalize_product_key 집합.
    """
    key = normalize_product_key(sourcing_url or "")
    existing = {k for k in (existing_source_keys or [])}
    return "update" if key in existing else "new"


# ── 파일럿 계획 (등록 직전 정지 — 부작용 0) ─────────────────────────────────────
def plan_pilot(join_rows: list, n: int = 50, prefer: str = "shopify_d2c",
               exclude_sources: Iterable[str] = ("rakuten",)) -> dict:
    """파일럿 대상 선정 — 매칭분 중 prefer 소스 우선, 라쿠텐 제외(서버 크롤 차단). 부작용 0(계획만).

    반환: {selected:[JoinRow…], count, prefer, excluded_rakuten, by_source}. **등록은 하지 않는다.**
    """
    exclude = set(exclude_sources or [])
    usable = [r for r in (join_rows or []) if r.source not in exclude]
    usable.sort(key=lambda r: 0 if r.source == prefer else 1)     # prefer 소스 앞으로(안정 정렬)
    selected = usable[:max(0, int(n))]
    by_source = {}
    for r in selected:
        by_source[r.source] = by_source.get(r.source, 0) + 1
    excluded_rakuten = sum(1 for r in (join_rows or []) if r.source == "rakuten")
    return {"selected": selected, "count": len(selected), "prefer": prefer,
            "excluded_rakuten": excluded_rakuten, "by_source": by_source,
            "note": "마켓 등록 직전 정지 — 오너 검수 후 일괄 등록 클릭(비가역 게이트)"}


# ── 접근성 게이트 (라이브 실행 전 정직 확인) ────────────────────────────────────
def access_status() -> dict:
    """라이브 조인/파일럿에 필요한 자산·자격 존재 여부 — 없으면 가짜 수치 대신 이 보고를 낸다."""
    sm = load_sourcing_map()
    # 계정별 쿠팡 자격(이 서버엔 없음이 기본). 단일 env는 어느 계정인지 불명 → 계정별 명시 env 권장.
    def _acct_ready(prefix: str) -> bool:
        return all(os.getenv(f"{prefix}_{k}") for k in ("VENDOR_ID", "ACCESS_KEY", "SECRET_KEY"))
    base_ready = all(os.getenv(f"COUPANG_{k}") for k in ("VENDOR_ID", "ACCESS_KEY", "SECRET_KEY"))
    accounts = {name: (_acct_ready(f"COUPANG_{name.upper()}") or base_ready) for name in ("고가네", "우주대행")}
    relay = bool(os.getenv("MARKET_RELAY_URL"))
    ready = sm["available"] and any(accounts.values())
    return {
        "ready": ready,
        "sourcing_map": {"available": sm["available"], "path": sm.get("path"), "count": sm["count"]},
        "coupang_accounts": accounts,          # 계정별 자격 준비 여부
        "relay": relay,                        # 쿠팡 IP 허용용 릴레이(고정 IP)
        "missing": [m for m, ok in [
            ("sourcing_map.json", sm["available"]),
            ("coupang 자격(2계정 중 1+)", any(accounts.values())),
            ("MARKET_RELAY_URL(쿠팡 IP 허용)", relay),
        ] if not ok],
        "owner_action": "sourcing_map 배치(SOURCING_MAP_PATH) + 계정별 COUPANG_고가네_*/COUPANG_우주대행_* + 릴레이 IP 등록 후 라이브 조인 실행",
    }


def run_inventory_join(fetch_items_fn=None, sourcing_map: Optional[dict] = None) -> dict:
    """라이브 조인 진입점 — **접근성 게이트 통과 시에만** 실행. 미충족이면 가짜 수치 대신 access 보고.

    fetch_items_fn(): 쿠팡 판매중 목록을 [{account, seller_product_id, external_vendor_sku, title}]로
      반환하는 함수(주입 — 실제는 계정별 CoupangAdapter.fetch_inventory 래핑, 읽기 전용). 미주입이면
      라이브 어댑터가 필요하나 이 코어는 호출하지 않는다(우회/발명 금지) → not-ready 보고.
    sourcing_map: 미지정이면 load_sourcing_map()으로 로드.
    """
    sm = {"available": True, "map": sourcing_map} if sourcing_map is not None else load_sourcing_map()
    st = access_status()
    if not sm.get("available") or fetch_items_fn is None:
        return {"ok": False, "reason": "라이브 조인 미준비 — 자산/자격 필요(가짜 수치 0)", "access": st}
    items = fetch_items_fn() or []
    rep = join_inventory(items, sm.get("map") or {})
    return {"ok": True, "report": rep.as_table(), "rows": rep.rows, "access": st}


# ── 파일럿 인입 오케스트레이션 (작업 2+3 배선 — 등록 직전 정지) ──────────────────
IMAGE_CAP = 2                          # 오너: 이미지 상품당 2장(Bluehost 디스크 4중 재발방지).


def _cost_krw_of(draft: dict):
    """수집 draft에서 원가(KRW) 추출. KRW면 그 값, 외화면 None(정직 — fx 미상, 가짜 환산 0)."""
    price = draft.get("price")
    cur = (draft.get("currency") or "").upper()
    try:
        val = float(str(price).replace(",", "")) if price not in (None, "") else None
    except (TypeError, ValueError):
        val = None
    if val is None or val <= 0:
        return None
    return val if cur in ("KRW", "") else None


def run_pilot_ingest(pilot_rows, *, channel, collect_fn, prevalidate_fn=None,
                     existing_source_keys=None, blacklist=None,
                     margin_rate: float = DEFAULT_MARGIN_RATE, image_cap: int = IMAGE_CAP) -> dict:
    """파일럿 행을 **기존 수집 경로로 인입 → 가격 → 사전검증**까지, **등록은 하지 않는다**(비가역 게이트).

    의존성 주입(테스트/발명 금지): collect_fn(url)→draft(기존 `_collect_real_draft`), prevalidate_fn(draft)→result.
    각 행: 취급금지 스킵 → 기존 채널 중복 스킵 → collect → 이미지 2장 캡 → 원가기준 가격 → 사전검증. registered=False 불변.
    """
    existing = set(existing_source_keys or [])
    rows_out, summ = [], {"ingested": 0, "skipped_forbidden": 0, "skipped_duplicate": 0,
                          "failed_collect": 0, "prevalidate_ok": 0, "prevalidate_fail": 0}
    for r in (pilot_rows or []):
        url = getattr(r, "sourcing_url", None) or (r.get("sourcing_url") if isinstance(r, dict) else "")
        title = getattr(r, "title", None) or (r.get("title") if isinstance(r, dict) else "")
        fb = is_forbidden(title, blacklist=blacklist)
        if fb:
            summ["skipped_forbidden"] += 1
            rows_out.append({"url": url, "action": "skipped-forbidden", "reason": fb, "registered": False})
            continue
        if dedup_decision(url, existing) == "update":      # 이미 채널에 있음(SUPERONE 등) → 스킵
            summ["skipped_duplicate"] += 1
            rows_out.append({"url": url, "action": "skipped-duplicate", "registered": False})
            continue
        draft = None
        try:
            draft = collect_fn(url)
        except Exception as exc:                           # 수집 실패는 정직 실패(가짜 성공 0)
            draft = None
        if not draft:
            summ["failed_collect"] += 1
            rows_out.append({"url": url, "action": "failed-collect", "registered": False})
            continue
        imgs = list(draft.get("images") or [])[:max(0, int(image_cap))]   # 이미지 2장 캡
        draft["images"] = imgs
        cost = _cost_krw_of(draft)
        price = recalc_channel_price(cost, channel, margin_rate=margin_rate) if cost is not None else \
            {"ok": False, "reason": "원가 미상(외화/빈값) — fx 확인 필요"}
        pv = prevalidate_fn(draft) if prevalidate_fn else {"ok": None, "reason": "prevalidate 미주입"}
        pv_ok = bool(getattr(pv, "ok", None) if not isinstance(pv, dict) else pv.get("ok"))
        summ["prevalidate_ok" if pv_ok else "prevalidate_fail"] += 1
        summ["ingested"] += 1
        rows_out.append({"url": url, "action": "ingested-prevalidated", "images": len(imgs),
                         "price": price, "prevalidate_ok": pv_ok, "registered": False})
    return {"registered": False,                            # ★ 등록 안 함(오너 클릭 게이트)
            "summary": summ, "rows": rows_out,
            "note": "마켓 등록 직전 정지 — 오너 검수 후 일괄 등록 클릭(비가역 게이트)"}

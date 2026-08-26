"""src/pipeline/register_pipe.py — 등록 파이프 이식 P1(검수표) + P3(승인 게이트·카나리 쿠팡 실등록).

Bluehost 수동 스크립트 등록을 콘솔 클릭 등록으로 이식. 서버 기존 자산 최대 재사용(발명 최소):
  - 수집: `_collect_real_draft`(도메인 dispatcher + 범용 스크래퍼 + 번역) 주입.
  - 정제/판정/가격: `clean_title_ko`·`is_forbidden`(blacklist 151)·`recalc_channel_price`(÷0.618 정합) 재사용.
P1 = 검수표(등록 없음). P3 = 검수 통과분을 **카나리 게이트**로 쿠팡 실등록(파일럿 register_pilot_rows 패턴).
"""
from __future__ import annotations

import json
import os
import re
from typing import Optional

from src.collectors.product_key import vendor_sku
from src.pipeline.coupang_replicate import (
    DEFAULT_MARGIN_RATE,
    IMAGE_CAP,
    clean_title_ko,
    is_forbidden,
    recalc_channel_price,
)

_KRW_CURRENCIES = frozenset({"KRW", "원", ""})

_FORBIDDEN_KIND_KO = {
    "blacklist": "금지어 목록",
    "forbidden-category": "금지 카테고리",
    "forbidden-term": "금지어 사전",
}

# ── ship_real 서버화 (소싱 6조건 §"등록 전 필수 — 한국 실배송 확인") ─────────────────
# 오너 수동 검증 전례: 소스 홈 HTML의 국가셀렉터에 value="KR"이 있어야 진짜 배송된다.
#   정책 페이지 "korea/worldwide" 문구만 믿으면 안 됨(myair0 = 정책상 국제배송인데 KR 없음 → 32건 등록 후 전량 중지).
#   이 검증으로 ALPAKA 130·ULANZI 84·HydraPak 36 = 250건을 등록 전에 걸렀다.
_KR_SHIP_BLOCKED_BRANDS = frozenset({"alpaka", "ulanzi", "hydrapak"})
_KR_MARKER = 'value="KR"'   # Shopify 홈 국가셀렉터 마커(실측)


def _brand_of(draft: dict, title: str) -> str:
    """초안에서 브랜드 추정(brand 필드 → 제목 첫 토큰). 배송불가 브랜드 매칭용."""
    b = str((draft or {}).get("brand") or "").strip()
    if b:
        return b
    return (title or "").strip().split(" ")[0] if title else ""


# ── 원산지 소스 우선순위(오너 지시·발명 금지·실측 우선) ────────────────────────────
#   ① 아마존 상세 Country of Origin 필드(스펙/본문 실측) · ② 브랜드 본사 국가(추정·라벨링) · ③ 없으면 보류.
_ORIGIN_LABEL_RE = re.compile(r"(country\s*of\s*origin|원산지|제조국)", re.I)
_ORIGIN_VALUE_RE = re.compile(
    r"(?:country\s*of\s*origin|원산지|제조국)\s*[:：]\s*([A-Za-z가-힣][A-Za-z가-힣 ]{0,20})", re.I)
_MADE_IN_RE = re.compile(r"made\s*in\s+([A-Za-z][A-Za-z ]{0,20})", re.I)


def _origin_from_detail(draft: dict) -> str:
    """수집 상세에서 'Country of Origin' 실측값 추출(아마존 상세 필드). specs 우선 → 본문 정규식."""
    for pair in (draft.get("specs") or []):
        try:
            label, value = pair[0], pair[1]
        except (TypeError, IndexError, KeyError):
            label, value = (pair.get("label"), pair.get("value")) if isinstance(pair, dict) else ("", "")
        if _ORIGIN_LABEL_RE.search(str(label or "")):
            v = str(value or "").strip()
            if v:
                return v
    text = " ".join(str(draft.get(k) or "") for k in
                    ("description", "description_en", "description_original", "detail_text", "text"))
    m = _ORIGIN_VALUE_RE.search(text)
    if m:
        return m.group(1).strip()
    m2 = _MADE_IN_RE.search(text)
    if m2:
        return m2.group(1).strip()
    return ""


_BRAND_COUNTRY_CACHE = {"loaded": False, "map": {}}


_BRAND_ORIGIN_PATHS = ("data/brand_origin.json", "data/brand_costs.json")


def load_brand_country_map(path: str = "") -> dict:
    """브랜드→본사국가 맵. `data/brand_origin.json`(전용 자산) → `brand_costs.json`(원가 자산) 순.

    스키마 유연: {"brands":{k:{country,...}}} · {k:{country|origin|hq_country}} · [{brand,country}].
    **country가 빈 값이면 로드 안 함**(불확실 → ② 비활성 → 폴백으로 내려감). 발명 금지 — 파일 값만.
    """
    paths = [path] if path else list(_BRAND_ORIGIN_PATHS)
    out = {}
    for p in paths:
        try:
            if not os.path.isfile(p):
                continue
            data = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, dict) and isinstance(data.get("brands"), dict):
            data = data["brands"]
        items = data.items() if isinstance(data, dict) else \
            [((x or {}).get("brand"), x) for x in (data or []) if isinstance(x, dict)]
        for b, v in items:
            if not b or str(b).startswith("_") or not isinstance(v, dict):
                continue
            c = v.get("country") or v.get("origin") or v.get("hq_country") or v.get("brand_country")
            c = str(c or "").strip()
            if c:                                  # 빈 값(불확실)은 건너뜀 — 폴백으로
                out.setdefault(str(b).strip().lower(), c)
        if out:
            break                                  # 앞 파일에서 얻었으면 뒤 파일은 폴백으로만
    return out


def _default_brand_country_fn(brand: str):
    """기본 브랜드→국가(캐시). brand_origin.json 로드 1회. 없으면 None(② 비활성 → 폴백)."""
    if not _BRAND_COUNTRY_CACHE["loaded"]:
        _BRAND_COUNTRY_CACHE["map"] = load_brand_country_map()
        _BRAND_COUNTRY_CACHE["loaded"] = True
    m = _BRAND_COUNTRY_CACHE["map"]
    b = str(brand or "").strip().lower()
    if not b:
        return None
    if b in m:
        return m[b]
    # 제목 부분일치(오너 승인) — sourcing_map에 brand 필드가 없고 아마존 brand 추출도 불안정하므로
    #   blacklist와 같은 방식으로 제목/브랜드 문자열 안에서 브랜드 키를 찾는다. 긴 키 우선(오탐 최소).
    for key in sorted(m, key=len, reverse=True):
        if len(key) >= 4 and key in b:
            return m[key]
    return None


_ORIGIN_SOURCE_KO = {
    "collected": "실측(수집)", "amazon_field": "실측(아마존 상세)",
    "brand_inferred": "추정(브랜드 본사국)", "fallback": "임시(폴백)", "none": "미확인",
}

# 폴백 원산지 문구(오너 지시: 원산지 미확인 = 등록 보류 **폐기**). 쿠팡이 어느 문구를 받는지는
#   카나리 응답이 실측 — 거부되면 응답 원문의 허용 문구로 env COUPANG_ORIGIN_FALLBACK 교체(1분 작업).
_ORIGIN_FALLBACK_DEFAULT = "해외"


def origin_fallback() -> str:
    """등록 폴백 원산지 문구. env `COUPANG_ORIGIN_FALLBACK`(기본 '해외'). 빈 문자열로 두면 폴백 비활성(=보류)."""
    v = os.getenv("COUPANG_ORIGIN_FALLBACK")
    if v is None:
        return _ORIGIN_FALLBACK_DEFAULT
    return v.strip()                       # 명시적 빈 값 = 폴백 끔(보류 복귀)


def resolve_origin(draft: dict, *, brand_country_fn=None, fallback=None) -> tuple:
    """원산지 우선순위 해석. 반환: (origin:str, origin_source:str).

    **층위 3단(섞지 않음 — 어느 층위로 채웠는지 항상 표기):**
      ① 실측 — 수집 명시(origin/brand_country)=collected · 아마존 상세 Country of Origin=amazon_field
      ② 추정 — 브랜드 본사국(brand_country_fn/brand_origin.json)=brand_inferred
      ③ 임시 — 폴백 문구(env COUPANG_ORIGIN_FALLBACK)=fallback  ← 보류 대신 등록 시도(오너 지시)
    폴백까지 비활성(빈 문자열)이면 none(=보류). 실측 > 추정 > 폴백 순서는 불변.
    """
    explicit = str((draft or {}).get("origin") or (draft or {}).get("brand_country") or "").strip()
    if explicit:
        return explicit, "collected"
    amz = _origin_from_detail(draft or {})
    if amz:
        return amz, "amazon_field"
    fn = brand_country_fn or _default_brand_country_fn
    title_s = (draft or {}).get("title_ko") or (draft or {}).get("title") or ""
    # 브랜드 필드 우선 → **제목 부분일치**(오너 승인: sourcing_map에 brand 필드 부재·아마존 brand 추출 불안정).
    for probe in (_brand_of(draft or {}, title_s), title_s):
        if not probe:
            continue
        try:
            bc = fn(probe)
        except Exception:
            bc = None
        if bc:
            return str(bc).strip(), "brand_inferred"
    # ③ 임시 폴백 — 보류 폐기(오너 지시). 값은 채우되 **fallback 층위로 표기**(실측·추정과 섞지 않음).
    fb = origin_fallback() if fallback is None else str(fallback or "").strip()
    if fb:
        return fb, "fallback"
    return "", "none"


# ── IPR 리스크 경고 계층(오너 지시) — blacklist(등록 차단)와 **다른 층위**. 차단 아님·표기만, 판단은 오너. ──
#   근거: 볼트 [[취급 금지 카테고리]] 애플 사전승인 반려 전례 · TORRAS 소명 이력.
_APPLE_COMPAT_RE = re.compile(
    r"아이폰|iphone|맥세이프|magsafe|에어팟|airpod|아이패드|ipad|애플\s*워치|apple\s*watch|"
    r"라이트닝|lightning|맥북|macbook|\bapple\b|애플", re.I)


def load_ipr_watch_brands() -> set:
    """소명 진행 중 브랜드 목록 — **env `IPR_WATCH_BRANDS`(쉼표/파이프) + `data/ipr_watch_brands.json`**.

    하드코딩 금지(오너 지시) — 오너가 볼트에서 관리해 env/파일로 배포. 미설정이면 빈 셋(경고 0).
    """
    brands = set()
    for b in re.split(r"[,|]", os.getenv("IPR_WATCH_BRANDS", "") or ""):
        b = b.strip().lower()
        if b:
            brands.add(b)
    try:
        if os.path.isfile("data/ipr_watch_brands.json"):
            data = json.load(open("data/ipr_watch_brands.json", encoding="utf-8"))
            seq = data if isinstance(data, list) else (data.get("brands") or [])
            for b in seq:
                b = str(b or "").strip().lower()
                if b:
                    brands.add(b)
    except Exception:
        pass
    return brands


def assess_warnings(title: str, brand: str = "", *, watch_brands=None) -> list:
    """IPR 리스크 경고(차단 아님·표기). 반환: [{kind, label, reason}].

    ① 애플 호환 표기(iPhone/MagSafe/AirPods 등) → 애플 사전승인 반려 전례 경고. **삼성/픽셀 전용은 무경고**
       (애플 토큰 없으면 매칭 안 됨). ② 소명 진행 브랜드(env/파일) → 경고.
    """
    text = f"{brand or ''} {title or ''}"
    warnings = []
    if _APPLE_COMPAT_RE.search(text):
        warnings.append({"kind": "apple_compat", "label": "애플 호환",
                         "reason": "애플 카테고리 사전승인 반려 전례 — 등록 전 확인(iPhone 대상 보류·삼성/픽셀용 유효)"})
    wb = watch_brands if watch_brands is not None else load_ipr_watch_brands()
    tl = text.lower()
    matched = next((w for w in wb if w and w in tl), None)
    if matched:
        warnings.append({"kind": "ipr_watch", "label": "소명 진행 브랜드",
                         "reason": f"IPR 소명 진행 중({matched}) — 등록 전 확인"})
    return warnings


def origin_coverage(titles, *, brand_country_fn=None, fallback=None) -> dict:
    """원산지 층위 **커버리지 실측** — 제목 목록에 대해 각 층위로 몇 건이 채워지는지.

    오너 검수용 표: ②(brand_inferred)로 채워진 건수 / ③(fallback)으로 간 건수 / 미확인.
    실측(collected/amazon_field)은 제목만으론 알 수 없어 여기선 ②③만 센다(수집 draft 없이 사이징).
    """
    counts = {"brand_inferred": 0, "fallback": 0, "none": 0}
    by_brand, samples = {}, {"brand_inferred": [], "fallback": []}
    total = 0
    for t in (titles or []):
        t = str(t or "").strip()
        if not t:
            continue
        total += 1
        origin, src = resolve_origin({"title": t}, brand_country_fn=brand_country_fn, fallback=fallback)
        counts[src] = counts.get(src, 0) + 1
        if src == "brand_inferred":
            by_brand[origin] = by_brand.get(origin, 0) + 1
        if len(samples.get(src, [])) < 5:
            samples.setdefault(src, []).append({"title": t[:60], "origin": origin})
    pct = (lambda n: round(100.0 * n / total, 1) if total else 0.0)
    return {
        "total": total,
        "brand_inferred": counts.get("brand_inferred", 0),
        "brand_inferred_pct": pct(counts.get("brand_inferred", 0)),
        "fallback": counts.get("fallback", 0),
        "fallback_pct": pct(counts.get("fallback", 0)),
        "none": counts.get("none", 0),
        "by_country": dict(sorted(by_brand.items(), key=lambda x: -x[1])),
        "brand_map_size": len(load_brand_country_map()),
        "samples": samples,
    }


def kr_ship_viability(brand: str, title: str = "", url: str = "", *, check_fn=None) -> dict:
    """한국 실배송 가능 판정. **등록 차단 안 함 — 플래그만**(오너 지시).

    판정 순서:
      1) 배송불가 전례 브랜드(ALPAKA·ULANZI·HydraPak) → viable=False("배송불가").
      2) check_fn 주입 시(url) 홈 HTML value="KR" 실측 — True/False. check_fn=(status, body) 튜플 반환
         가능(ship_real get 튜플 지뢰) → 안전 언패킹. 예외/조회불가 → 미검증.
      3) 그 외 → viable=None("미검증", 실측 불가·정직).
    반환 {viable(bool|None), status, reason}.
    """
    text = f"{brand} {title}".lower()
    for bad in _KR_SHIP_BLOCKED_BRANDS:
        if bad in text:
            return {"viable": False, "status": "배송불가",
                    "reason": f"{bad.upper()} 전례 — 한국 미배송(등록 전 차단 권고)"}
    if check_fn and url:
        try:
            res = check_fn(url)
            body = res
            if isinstance(res, (tuple, list)) and len(res) >= 2:   # (status, body) 언패킹
                body = res[1]
            body = "" if body is None else str(body)
            if _KR_MARKER in body:
                return {"viable": True, "status": "배송가능", "reason": "홈 국가셀렉터 KR 확인(실측)"}
            if body:
                return {"viable": False, "status": "배송불가",
                        "reason": "홈 국가셀렉터에 KR 없음(정책 문구만으론 미신뢰)"}
        except Exception as exc:
            return {"viable": None, "status": "미검증", "reason": f"실배송 조회 실패: {exc}"}
    return {"viable": None, "status": "미검증", "reason": "실배송 미조회(라이브 확인 필요)"}


def _real_margin(sale_krw, cost_krw, fee_rate, ship_cost_krw):
    """실마진(순이익 KRW, 마진율%) — **단일 소스 MarginCalculator._calc_margin 재사용**(새 공식 0).

    랜딩코스트 = 원가 + 국내배송(있으면). 채널 수수료율 반영. 판매가 미상/원가 미상이면 (None, None).
    """
    if not sale_krw or cost_krw is None or fee_rate is None:
        return None, None
    from decimal import Decimal
    from src.seller_console.margin_calculator import MarginCalculator
    landed = Decimal(str(cost_krw)) + Decimal(str(ship_cost_krw or 0))
    fee_frac = Decimal(str(fee_rate)) / Decimal("100")
    net_krw, margin_pct = MarginCalculator._calc_margin(Decimal(str(sale_krw)), landed, fee_frac)
    return int(net_krw), float(round(margin_pct, 1))


def explain_forbidden(reason: Optional[str], title: str) -> Optional[dict]:
    """취급금지 사유(is_forbidden 반환)를 **매칭 토큰 원문 + 제목의 걸린 위치**로 풀어낸다.

    오너가 표에서 오탐(예: 토라스 'Chanel' 패턴명, '샤넬패턴'처럼 브랜드 아닌 부분일치)을 즉석 판별하도록.
    반환 {kind, kind_ko, term, matched(제목 내 실제 걸린 부분문자열), snippet(맥락⟦걸린곳⟧)}.
    """
    if not reason:
        return None
    kind, _, term = str(reason).partition(":")
    term = term.strip()
    matched, snippet = "", ""
    if term and title:
        idx = title.lower().find(term.lower())
        if idx >= 0:
            end = idx + len(term)
            matched = title[idx:end]
            s, e = max(0, idx - 8), min(len(title), end + 8)
            snippet = (("…" if s > 0 else "") + title[s:idx] + "⟦" + matched + "⟧"
                       + title[end:e] + ("…" if e < len(title) else ""))
    return {"kind": kind, "kind_ko": _FORBIDDEN_KIND_KO.get(kind, kind),
            "term": term, "matched": matched, "snippet": snippet}


def build_source_review_row(draft: dict, *, url: str = "", channel: str = "woocommerce_multishop",
                            blacklist=None, margin_rate: float = DEFAULT_MARGIN_RATE,
                            fx_rate: Optional[float] = None, fx_rates: Optional[dict] = None,
                            ship_check_fn=None, ship_cost_fn=None,
                            brand_country_fn=None, watch_brands=None) -> dict:
    """수집 초안(draft) → 검수표 1행(파일럿 동형). **등록 안 함**(registered=False 불변).

    - 제목: 번역 초안(title_ko) 재정제(clean_title_ko) + 절단/CJK 플래그(조용히 자르지 않음).
    - 취급판정: is_forbidden(blacklist 151 + 금지 카테고리) — 미통과=excluded+사유(조용한 탈락 금지).
    - 가격: 원가 KRW 확보 시 recalc_channel_price(÷0.618 정합). 외화+환율 미상=가짜 환산 0(미입력 정직).
    - **P2 배송(ship_real):** 한국 실배송 판정(플래그만 — 등록 차단 안 함). 배송불가 전례 브랜드/실측/미검증.
    - **P2 마진 정밀화:** margin_pct = 채널 수수료·배송비 반영 **실마진**(MarginCalculator 단일 소스, 27.4% 근사 아님).
      배송비 > 원가 35%면 ship_over_35pct(소싱 6조건 §6 위반). target_margin_pct = 목표 마진(27.4).
    """
    title = (draft.get("title_ko") or draft.get("title_en") or draft.get("title") or "").strip()
    fb = is_forbidden(title, blacklist=blacklist)
    currency = str(draft.get("currency") or "").upper()
    try:
        price_original = float(draft.get("price_original") or draft.get("price") or 0) or None
    except (TypeError, ValueError):
        price_original = None

    # 환율은 **그 통화의 환율**만 쓴다(EUR 상품에 USD 환율 = 임의 환산 → 금지). 없으면 미입력 정직.
    if isinstance(fx_rates, dict):
        try:
            rate = float(fx_rates.get(currency) or 0) or None    # 통화 미수록 = 환산 불가(정직)
        except (TypeError, ValueError):
            rate = None
    else:
        rate = fx_rate                                            # 단일 환율(구 호출부 호환)

    cost_krw = None
    if price_original:
        if currency in _KRW_CURRENCIES:
            cost_krw = round(price_original)
            cost_basis = "원화 원가"
        elif rate:
            cost_krw = round(price_original * rate)
            cost_basis = f"{currency}×환율 환산"
        else:
            cost_basis = f"{currency} 원가 — 환율 미상(환산 불가·미입력)"
    else:
        cost_basis = "원가 미입력(수집가 없음)"

    price = recalc_channel_price(cost_krw, channel, margin_rate=margin_rate) if cost_krw \
        else {"ok": False, "reason": cost_basis}
    ct = clean_title_ko(title, url=url)
    images = [i for i in (draft.get("images") or []) if i]

    # ── 배송(ship_real) — 플래그만(등록 차단 안 함) ──────────────────────────────
    brand = _brand_of(draft, title)
    ship = kr_ship_viability(brand, title, url, check_fn=ship_check_fn)

    # ── 고시정보 미리보기(P3 카나리 반려 대응) — 등록 전 오너가 실값을 본다. 발명 금지·사실만. ──
    #   원산지 소스 우선순위(오너): ①아마존 상세 실측 → ②브랜드 본사국 추정(라벨) → ③없으면 보류.
    origin, origin_source = resolve_origin(draft, brand_country_fn=brand_country_fn)
    notice_preview = {
        "제조자": brand or "미확인",
        "수입자": "고가네",                                   # 기본 계정 상호(우주대행 등록 시 교체)
        "원산지": origin or "미확인 — 등록 보류",
        "origin_verified": origin_source in ("collected", "amazon_field"),   # 실측 층위만 검증됨
        "origin_source": origin_source,            # collected/amazon_field/brand_inferred/fallback/none
        "origin_source_ko": _ORIGIN_SOURCE_KO.get(origin_source, origin_source),
        "origin_inferred": origin_source == "brand_inferred",  # 추정(브랜드 본사국)
        "origin_fallback": origin_source == "fallback",        # 임시 폴백 — 등록은 하되 오너가 식별
        "AS연락처": "판매자 연락처(설정값)",
        "인증": "인증 대상 아님(실측 확인 필요)",
    }
    # 보류는 **폴백까지 비활성**일 때만(오너 지시: 원산지 미확인 = 보류 폐기).
    notice_hold = (origin_source == "none")

    # ── 배송비(국내) — 주입 hook. 미상이면 미반영(마진에 0)·정직 표기 ────────────────
    ship_cost_krw = None
    if ship_cost_fn and cost_krw:
        try:
            v = ship_cost_fn(cost_krw=cost_krw, brand=brand, title=title, url=url)
            ship_cost_krw = round(float(v)) if v is not None else None
        except Exception:
            ship_cost_krw = None
    ship_over_35pct = bool(ship_cost_krw and cost_krw and ship_cost_krw > 0.35 * cost_krw)

    # ── 실마진 — 단일 소스(MarginCalculator). 27.4% 근사 교체 ─────────────────────
    sale_krw = price.get("sale_price_krw") if price.get("ok") else None
    fee_rate = price.get("fee_rate") if price.get("ok") else None
    net_krw, real_margin_pct = _real_margin(sale_krw, cost_krw, fee_rate, ship_cost_krw)

    return {
        "url": url,
        "title_ko": ct["title"], "title_original": draft.get("title_en") or draft.get("title") or "",
        "title_truncated": ct["truncated"], "title_truncated_suspect": ct["truncated_suspect"],
        "title_cjk_residual": ct["cjk_residual"], "title_cleaned": ct["changed"],
        "price_original": price_original, "currency": currency,
        "cost_krw": cost_krw, "cost_basis": cost_basis,
        "sale_krw": sale_krw,
        "margin_pct": real_margin_pct,                 # 실마진(채널 수수료·배송비 반영, 단일 소스)
        "target_margin_pct": price.get("margin_rate") if price.get("ok") else None,  # 목표(27.4)
        "fee_rate": fee_rate, "net_krw": net_krw,
        "ship_cost_krw": ship_cost_krw,
        "ship_cost_basis": ("국내배송 반영" if ship_cost_krw else "배송비 미상(마진 미반영)"),
        "ship_over_35pct": ship_over_35pct,            # 소싱 6조건 §6 위반(배송비>원가 35%)
        "ship_viable": ship["viable"], "ship_status": ship["status"], "ship_reason": ship["reason"],
        "price_reason": None if price.get("ok") else price.get("reason"),
        "target_channel": channel,
        "image_count": len(images), "thumbnail": (images[0] if images else ""),
        "source": draft.get("source") or draft.get("adapter_used"),
        "brand": brand, "origin": origin, "origin_source": origin_source,   # 고시정보 실값(등록 시 uploader가 사용)
        "notice_preview": notice_preview, "notice_hold": notice_hold,   # 고시정보 미리보기 + 원산지 보류
        "warnings": assess_warnings(title, brand, watch_brands=watch_brands),   # IPR 경고(차단 아님·표기)
        "forbidden": fb, "forbidden_detail": explain_forbidden(fb, title),
        "excluded": bool(fb), "registered": False,
    }


def build_source_review(urls, *, collect_fn, channel: str = "woocommerce_multishop",
                        blacklist=None, margin_rate: float = DEFAULT_MARGIN_RATE,
                        fx_rate: Optional[float] = None, fx_rates: Optional[dict] = None,
                        cap: int = 50,
                        ship_check_fn=None, ship_cost_fn=None, brand_country_fn=None,
                        watch_brands=None) -> dict:
    """소싱 URL 목록 → 검수표. collect_fn(url)=서버 수집(주입). **등록 없음.**

    수집 실패/취급금지는 조용히 버리지 않고 failed/excluded로 사유와 함께 분리.
    """
    seen, review, failed = set(), [], []
    clean_urls = []
    for u in (urls or []):
        u = str(u or "").strip()
        if u and u not in seen:
            seen.add(u)
            clean_urls.append(u)
    for u in clean_urls[:cap]:
        try:
            draft = collect_fn(u)
        except Exception as exc:                       # 수집 예외 = 정직 실패(조용한 탈락 금지)
            failed.append({"url": u, "reason": f"수집 예외: {exc}"})
            continue
        if not draft:
            failed.append({"url": u, "reason": "수집 실패(실데이터 못 얻음) — 확장 수집/직접 입력 권장"})
            continue
        review.append(build_source_review_row(draft, url=u, channel=channel, blacklist=blacklist,
                                               margin_rate=margin_rate, fx_rate=fx_rate,
                                               fx_rates=fx_rates,
                                               ship_check_fn=ship_check_fn, ship_cost_fn=ship_cost_fn,
                                               brand_country_fn=brand_country_fn, watch_brands=watch_brands))
    return {
        "count": len(review),
        "review_pass": [r for r in review if not r["excluded"]],
        "excluded": [r for r in review if r["excluded"]],
        "failed": failed,
        "requested": len(clean_urls),
        "capped": len(clean_urls) > cap,
    }


# ── P3: 승인 게이트 + 카나리 쿠팡 실등록 (파일럿 register_pilot_rows 패턴) ──────────
_REGISTER_PIPE_APPROVED_DEFAULT = True   # 오너 "allow 승인"(2026-08-22). 안전은 카나리 게이트로 이관.


def register_pipe_approved() -> bool:
    """P3 실등록 승인 여부. env `REGISTER_PIPE_APPROVED` 우선(미설정=오너 승인 기본). 안전=카나리."""
    v = os.getenv("REGISTER_PIPE_APPROVED", "").strip().lower()
    if v:
        return v in ("1", "true", "yes", "on")
    return _REGISTER_PIPE_APPROVED_DEFAULT


def _res_field(res, key, *alts):
    if isinstance(res, dict):
        for k in (key,) + alts:
            if k in res:
                return res[k]
        return None
    for k in (key,) + alts:
        if hasattr(res, k):
            return getattr(res, k)
    return None


def register_source_rows(rows, *, dispatch_fn, enrich_fn=None, account: str = "gogane",
                         n: int = 1, batch_ok: bool = False, approved: Optional[bool] = None,
                         sleep_fn=None, sleep_sec: float = 0.6, record_fn=None,
                         lookup_fn=None) -> dict:
    """P1 검수 통과분 → **쿠팡 실등록**. 승인 게이트 + **카나리(기본 1건)** + 롤백 금지 + 행별 사유.

    - **비가역 방어:** approved 아니면 등록 0(정직 차단). batch_ok=False면 첫 1건만(카나리), 전량은
      육안 확인 후 batch_ok=1로만. 부분 실패 시 성공분 유지(롤백 금지)·조용한 실패 금지(행별 registered+사유).
    - **이미지 0장은 등록 안 함**(안 팔릴 상품 — P1/파일럿 정책 일관).
    - dispatch_fn(product_data, account)→ 등록 결과({success, product_id, url, error} 또는 동형 객체).
      enrich_fn(row)→{images, description_html, category_code} 재수집(이미지·상세). 둘 다 주입(발명 0·오프라인).
    - **record_fn(dict)**: 등록 성공분을 **등록 대장**에 적재(P4 반려감시가 감시 대상을 스스로 알게).
      주입식이라 파이프라인은 저장소를 모른다(오프라인 계약 검증 가능). 적재 실패는 행에 사유 표기.
    - **lookup_fn(sku, account)**: 이미 등록된 건 조회 → 있으면 **신규 등록 안 함**(중복 방지).
      반려 수리는 신규 POST가 아니라 **기존 sid 재제출**이 정석이라, 여기서 막고 경로를 안내한다.
    """
    if approved is None:
        approved = register_pipe_approved()
    if not approved:
        return {"ok": False, "approved": False,
                "error": "REGISTER_PIPE_APPROVED 미승인 — 실등록 차단(안전 게이트)"}
    if account not in ("gogane", "woojoo"):
        return {"ok": False, "error": f"알 수 없는 계정: {account} (gogane/woojoo)"}

    import time as _t
    sleep_fn = sleep_fn or _t.sleep
    passable = [r for r in (rows or []) if not r.get("excluded")]
    passable = passable[:1] if not batch_ok else passable[:max(0, int(n))]
    results = []
    for i, r in enumerate(passable):
        if i and sleep_sec:
            sleep_fn(sleep_sec)                          # 레이트리밋 예의(호출 간격)
        images, desc, cat = [], "", r.get("category_code")
        if enrich_fn:
            try:
                e = enrich_fn(r) or {}
                images = list(e.get("images") or [])[:IMAGE_CAP]
                desc = e.get("description_html") or ""
                cat = e.get("category_code") or cat
            except Exception as exc:                     # 수집 실패 = 정직 실패(등록 안 함), 다음 행 계속
                results.append({"url": r.get("url"), "title": r.get("title_ko"), "registered": False,
                                "reason": f"collect 실패: {exc}", "image_count": 0, "product_id": None})
                continue
        if not images:                                   # 이미지 0장 → 등록 보류(안 팔릴 상품 공개 방지)
            results.append({"url": r.get("url"), "title": r.get("title_ko"), "registered": False,
                            "reason": "이미지 0장 — 등록 보류(수집 실패, 확장 수집 권장)",
                            "image_count": 0, "product_id": None})
            continue
        # 판매가 미확정(환율 미상 등) → 등록 안 함. 0원 전송은 마켓이 반드시 거부한다(왕복 절약·정직 사유).
        try:
            _sale = int(r.get("sale_krw") or 0)
        except (TypeError, ValueError):
            _sale = 0
        if _sale < 10:
            results.append({"url": r.get("url"), "title": r.get("title_ko"), "registered": False,
                            "reason": (f"판매가 미확정({r.get('sale_krw')!r}) — 등록 보류. "
                                       + (r.get("price_reason") or "검수표 판매가를 확인하세요.")),
                            "image_count": len(images), "product_id": None})
            continue
        # 판매자 SKU(마켓 옵션명·externalVendorSku) — URL 파편 전송 금지. 못 뽑으면 등록 중단.
        sku = vendor_sku(r.get("url") or "")
        if not sku:
            results.append({"url": r.get("url"), "title": r.get("title_ko"), "registered": False,
                            "reason": "SKU 추출 실패 — 등록 보류(상품 URL에서 식별자를 뽑지 못했습니다).",
                            "image_count": len(images), "product_id": None})
            continue
        # **중복 등록 방지(오너 지시):** 이미 등록된 상품이면 신규 POST를 하지 않는다.
        #   반려 수리는 신규 등록이 아니라 **기존 sid PUT 수정 + PUT approvals**가 정석이다.
        #   여기서 막고 재제출 경로를 사유로 안내한다(같은 상품 두 건이 마켓에 뜨는 것을 방지).
        if lookup_fn:
            try:
                known = lookup_fn(sku, account)
            except Exception:
                known = None                        # 조회 실패는 등록을 막지 않는다(가용성 우선·정직)
            if known and known.get("product_id"):
                st = str(known.get("status") or "")
                how = ("반려건입니다 — 재제출(기존 상품 수정 + 승인요청)로 처리하세요."
                       if st == "rejected" else "이미 등록된 상품입니다.")
                results.append({"url": r.get("url"), "title": r.get("title_ko"), "account": account,
                                "registered": False, "duplicate": True,
                                "product_id": known["product_id"], "existing_status": st,
                                "reason": f"{how} (상품번호 {known['product_id']}) — 신규 등록 안 함",
                                "image_count": len(images)})
                continue
        product_data = {
            "title_ko": r.get("title_ko"), "sell_price_krw": r.get("sale_krw"), "sku": sku,
            "images": images, "description_html": desc, "category_code": cat,
            "url": r.get("url"), "source": r.get("source"),
            "brand": r.get("brand"), "origin": r.get("origin"),   # 고시정보 실값(제조자/원산지)
        }
        try:
            res = dispatch_fn(product_data, account)
        except Exception as exc:                         # 롤백 금지 — 실패분만 기록하고 계속
            results.append({"url": r.get("url"), "title": r.get("title_ko"), "registered": False,
                            "reason": f"dispatch 예외: {exc}", "image_count": len(images), "product_id": None})
            continue
        ok = bool(_res_field(res, "success"))
        pid = (_res_field(res, "product_id") if ok else None)
        if ok and pid and record_fn:
            # 등록 대장 적재(P4 반려감시 소스) — 실패해도 등록 결과는 유지(롤백 금지·조용한 실패 금지).
            try:
                record_fn({"product_id": str(pid), "account": account, "vendor_sku": sku,
                           "title": r.get("title_ko") or "", "source_url": r.get("url") or "",
                           "market_url": _res_field(res, "url", "external_url") or ""})
            except Exception as exc:
                results.append({"url": r.get("url"), "title": r.get("title_ko"), "account": account,
                                "registered": True, "image_count": len(images), "product_id": str(pid),
                                "market_url": _res_field(res, "url", "external_url"),
                                "reason": None,
                                "registry_error": f"등록 대장 적재 실패(반려감시 누락 가능): {exc}"})
                continue
        results.append({
            "url": r.get("url"), "title": r.get("title_ko"), "account": account,
            "registered": ok, "image_count": len(images),
            "product_id": (str(pid) if ok and pid else None),
            "market_url": (_res_field(res, "url", "external_url") if ok else None),
            "reason": None if ok else (_res_field(res, "error", "message") or "쿠팡 등록 실패"),
        })
    return {
        "ok": True, "approved": True, "account": account,
        "mode": "canary" if not batch_ok else "batch",
        "target": len(passable), "batch_ok": bool(batch_ok),
        "registered": sum(1 for x in results if x["registered"]),
        "failed": sum(1 for x in results if not x["registered"] and not x.get("duplicate")),
        "duplicates": sum(1 for x in results if x.get("duplicate")),
        "results": results,
        "note": ("카나리 1건 — 쿠팡 승인심사 대기, 육안 확인 후 batch_ok=1로 속행"
                 if not batch_ok else f"배치 {len(passable)}건(쿠팡 승인심사 대기)"),
    }

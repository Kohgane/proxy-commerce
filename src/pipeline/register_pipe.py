"""src/pipeline/register_pipe.py — 등록 파이프 이식 P1(검수표) + P3(승인 게이트·카나리 쿠팡 실등록).

Bluehost 수동 스크립트 등록을 콘솔 클릭 등록으로 이식. 서버 기존 자산 최대 재사용(발명 최소):
  - 수집: `_collect_real_draft`(도메인 dispatcher + 범용 스크래퍼 + 번역) 주입.
  - 정제/판정/가격: `clean_title_ko`·`is_forbidden`(blacklist 151)·`recalc_channel_price`(÷0.618 정합) 재사용.
P1 = 검수표(등록 없음). P3 = 검수 통과분을 **카나리 게이트**로 쿠팡 실등록(파일럿 register_pilot_rows 패턴).
"""
from __future__ import annotations

import os
from typing import Optional

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
                            fx_rate: Optional[float] = None) -> dict:
    """수집 초안(draft) → 검수표 1행(파일럿 동형). **등록 안 함**(registered=False 불변).

    - 제목: 번역 초안(title_ko) 재정제(clean_title_ko) + 절단/CJK 플래그(조용히 자르지 않음).
    - 취급판정: is_forbidden(blacklist 151 + 금지 카테고리) — 미통과=excluded+사유(조용한 탈락 금지).
    - 가격: 원가 KRW 확보 시 recalc_channel_price(÷0.618 정합). 외화+환율 미상=가짜 환산 0(미입력 정직).
    """
    title = (draft.get("title_ko") or draft.get("title_en") or draft.get("title") or "").strip()
    fb = is_forbidden(title, blacklist=blacklist)
    currency = str(draft.get("currency") or "").upper()
    try:
        price_original = float(draft.get("price_original") or draft.get("price") or 0) or None
    except (TypeError, ValueError):
        price_original = None

    cost_krw = None
    if price_original:
        if currency in _KRW_CURRENCIES:
            cost_krw = round(price_original)
            cost_basis = "원화 원가"
        elif fx_rate:
            cost_krw = round(price_original * fx_rate)
            cost_basis = f"{currency}×환율 환산"
        else:
            cost_basis = f"{currency} 원가 — 환율 미상(환산 불가·미입력)"
    else:
        cost_basis = "원가 미입력(수집가 없음)"

    price = recalc_channel_price(cost_krw, channel, margin_rate=margin_rate) if cost_krw \
        else {"ok": False, "reason": cost_basis}
    ct = clean_title_ko(title, url=url)
    images = [i for i in (draft.get("images") or []) if i]
    return {
        "url": url,
        "title_ko": ct["title"], "title_original": draft.get("title_en") or draft.get("title") or "",
        "title_truncated": ct["truncated"], "title_truncated_suspect": ct["truncated_suspect"],
        "title_cjk_residual": ct["cjk_residual"], "title_cleaned": ct["changed"],
        "price_original": price_original, "currency": currency,
        "cost_krw": cost_krw, "cost_basis": cost_basis,
        "sale_krw": price.get("sale_price_krw") if price.get("ok") else None,
        "margin_pct": price.get("margin_rate") if price.get("ok") else None,
        "price_reason": None if price.get("ok") else price.get("reason"),
        "target_channel": channel,
        "image_count": len(images), "thumbnail": (images[0] if images else ""),
        "source": draft.get("source") or draft.get("adapter_used"),
        "forbidden": fb, "forbidden_detail": explain_forbidden(fb, title),
        "excluded": bool(fb), "registered": False,
    }


def build_source_review(urls, *, collect_fn, channel: str = "woocommerce_multishop",
                        blacklist=None, margin_rate: float = DEFAULT_MARGIN_RATE,
                        fx_rate: Optional[float] = None, cap: int = 50) -> dict:
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
                                               margin_rate=margin_rate, fx_rate=fx_rate))
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
                         sleep_fn=None, sleep_sec: float = 0.6) -> dict:
    """P1 검수 통과분 → **쿠팡 실등록**. 승인 게이트 + **카나리(기본 1건)** + 롤백 금지 + 행별 사유.

    - **비가역 방어:** approved 아니면 등록 0(정직 차단). batch_ok=False면 첫 1건만(카나리), 전량은
      육안 확인 후 batch_ok=1로만. 부분 실패 시 성공분 유지(롤백 금지)·조용한 실패 금지(행별 registered+사유).
    - **이미지 0장은 등록 안 함**(안 팔릴 상품 — P1/파일럿 정책 일관).
    - dispatch_fn(product_data, account)→ 등록 결과({success, product_id, url, error} 또는 동형 객체).
      enrich_fn(row)→{images, description_html, category_code} 재수집(이미지·상세). 둘 다 주입(발명 0·오프라인).
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
        product_data = {
            "title_ko": r.get("title_ko"), "sell_price_krw": r.get("sale_krw"),
            "images": images, "description_html": desc, "category_code": cat,
            "url": r.get("url"), "source": r.get("source"),
        }
        try:
            res = dispatch_fn(product_data, account)
        except Exception as exc:                         # 롤백 금지 — 실패분만 기록하고 계속
            results.append({"url": r.get("url"), "title": r.get("title_ko"), "registered": False,
                            "reason": f"dispatch 예외: {exc}", "image_count": len(images), "product_id": None})
            continue
        ok = bool(_res_field(res, "success"))
        results.append({
            "url": r.get("url"), "title": r.get("title_ko"), "account": account,
            "registered": ok, "image_count": len(images),
            "product_id": (_res_field(res, "product_id") if ok else None),
            "market_url": (_res_field(res, "url", "external_url") if ok else None),
            "reason": None if ok else (_res_field(res, "error", "message") or "쿠팡 등록 실패"),
        })
    return {
        "ok": True, "approved": True, "account": account,
        "mode": "canary" if not batch_ok else "batch",
        "target": len(passable), "batch_ok": bool(batch_ok),
        "registered": sum(1 for x in results if x["registered"]),
        "failed": sum(1 for x in results if not x["registered"]),
        "results": results,
        "note": ("카나리 1건 — 쿠팡 승인심사 대기, 육안 확인 후 batch_ok=1로 속행"
                 if not batch_ok else f"배치 {len(passable)}건(쿠팡 승인심사 대기)"),
    }

"""src/pipeline/register_pipe.py — 등록 파이프 이식 P1: 소싱 URL → 수집·검증 → 검수표 (등록 없음).

Bluehost 수동 스크립트 등록을 콘솔 클릭 등록으로 이식하는 첫 단계. **등록은 절대 안 한다**(P3에서
카나리 게이트로 실등록 — 이 모듈은 검수표까지). 서버 기존 자산 최대 재사용(발명 최소):
  - 수집: `_collect_real_draft`(도메인 dispatcher + 범용 스크래퍼 + 번역) 주입.
  - 정제/판정/가격: `clean_title_ko`·`is_forbidden`(blacklist 151)·`recalc_channel_price`(÷0.618 정합) 재사용.
파일럿 검수표(`build_review_row`)와 **동형 출력** — 후속 P3가 같은 행으로 등록 실행.
"""
from __future__ import annotations

from typing import Optional

from src.pipeline.coupang_replicate import (
    DEFAULT_MARGIN_RATE,
    clean_title_ko,
    is_forbidden,
    recalc_channel_price,
)

_KRW_CURRENCIES = frozenset({"KRW", "원", ""})


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
        "forbidden": fb, "excluded": bool(fb), "registered": False,
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

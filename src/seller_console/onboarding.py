"""셀러 대시보드 온보딩 상태 계산 유틸."""
from __future__ import annotations

from typing import Any


def _safe_count(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def compute_onboarding_state(
    connected_markets: Any,
    source_count: Any,
    product_count: Any,
    *,
    collected_count: Any = None,
    dismissed: bool = False,
) -> dict[str, Any]:
    """활성화 퍼널 진행 상태를 계산한다.

    collected_count 제공 시(v25 P1) '상품 수집'을 첫 단계로 prepend해
    수집 → 마켓 연동 → 소싱처 → 첫 업로드(아하-모먼트) 퍼널을 만든다.
    None이면(레거시) 기존 마켓 연동 → 소싱처 → 상품 등록 3단계.
    """
    connected_count = _safe_count(connected_markets)
    sources = _safe_count(source_count)
    products = _safe_count(product_count)

    steps = []
    if collected_count is not None:
        collected = _safe_count(collected_count)
        steps.append({
            "key": "collect",
            "title": "첫 상품 수집",
            "description": "고가수집기로 해외 상품을 가져오고 ‘수집한 상품’에서 확인·편집하세요.",
            "href": "/seller/collect",
            "cta_label": "상품 수집하기",
            "completed": collected > 0,
        })
    steps += [
        {
            "key": "market",
            "title": "마켓 연동",
            "description": "쿠팡·네이버 등 최소 1개 마켓을 먼저 연결하세요.",
            "href": "/seller/markets",
            "cta_label": "지금 시작하기",
            "completed": connected_count > 0,
        },
        {
            "key": "source",
            "title": "첫 소싱처 등록",
            "description": "자주 쓰는 브랜드몰을 소싱처 등록소에 추가하세요.",
            "href": "/seller/sourcing",
            "cta_label": "소싱처 등록하기",
            "completed": sources > 0,
        },
        {
            "key": "product",
            "title": "🎯 첫 마켓 업로드",
            "description": "수집한 상품을 내 마켓에 올리면 끝! (가장 중요한 한 걸음)",
            "href": "/seller/collect/history",
            "cta_label": "수집한 상품 업로드",
            "completed": products > 0,
        },
    ]

    completed_steps = sum(1 for step in steps if step["completed"])
    total_steps = len(steps)
    progress_percent = int((completed_steps / total_steps) * 100) if total_steps else 0
    next_step_key = next((step["key"] for step in steps if not step["completed"]), None)

    for step in steps:
        step["is_next"] = bool(next_step_key and step["key"] == next_step_key)

    is_completed = completed_steps == total_steps
    return {
        "steps": steps,
        "completed_steps": completed_steps,
        "total_steps": total_steps,
        "progress_percent": progress_percent,
        "is_completed": is_completed,
        "dismissed": bool(dismissed),
        "visible": not dismissed and not is_completed,
        "show_completion_notice": not dismissed and is_completed,
    }

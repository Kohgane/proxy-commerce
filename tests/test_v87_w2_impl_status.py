"""tests/test_v87_w2_impl_status.py — v87-W2-impl 주문 상태 계층색 + 비색 단서.

## 오너 확정(A안, 제안서 #592 §7)
- 색이 9상태를 혼자 지지 못한다(색약·인접붙음) → 색은 '거친 계층(4)'만, 정밀 단계는 비-색 단서.
- 진행(신규→결제→준비→배송)=금 1색 + 단계 도트(1~4), 완료=청록+체크, 취소=먹뮤트+슬래시,
  되돌림(반품·교환·환불)=브론즈(≠오류 적색)+되돌림 아이콘. 마켓 색코딩 제거→뮤트(라벨이 구분자).

## 그레이스케일 판별 계약(핵심)
색을 지워도(같은 계층색끼리) 서로 다른 의미의 상태가 **비-색 단서**(도트 수·아이콘·라벨)만으로
전부 구분돼야 한다. 색약/흑백 인쇄에서도 정보 손실 0.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.order_webhook import app

_ALL = ["new", "paid", "preparing", "shipped", "delivered",
        "canceled", "returned", "exchanged", "refund_requested"]
_KO = {"new": "신규접수", "paid": "결제완료", "preparing": "상품준비중", "shipped": "배송중",
       "delivered": "배송완료", "canceled": "취소", "returned": "반품",
       "exchanged": "교환", "refund_requested": "환불요청"}


def _render(status, label):
    tmpl = app.jinja_env.from_string(
        "{% from '_status_badge.html' import status_badge %}{{ status_badge(s, l) }}")
    return tmpl.render(s=status, l=label)


def _color_class(html):
    m = re.search(r"pc-lc-(progress|done|cancel|return)", html)
    return m.group(0) if m else None


def _noncolor_signature(html):
    """색을 무시한 판별 단서: (채운 도트 수, 아이콘, 라벨텍스트)."""
    dots_on = len(re.findall(r"pc-lc-dot--on", html))
    icon = re.search(r"bi-([a-z0-9-]+)", html)
    label = re.sub(r"<[^>]+>", "", html).strip()
    return (dots_on, icon.group(1) if icon else None, label)


# ── 진행 4단계: 같은 금색, 도트 수 1~4로 구분(그레이스케일 생존) ──────
def test_progress_steps_distinguished_by_dot_count():
    counts = {}
    for s in ["new", "paid", "preparing", "shipped"]:
        html = _render(s, _KO[s])
        assert _color_class(html) == "pc-lc-progress"        # 4단계 동일 계층색(금)
        counts[s] = len(re.findall(r"pc-lc-dot--on", html))
    assert counts == {"new": 1, "paid": 2, "preparing": 3, "shipped": 4}  # 단조 증가
    assert len(set(counts.values())) == 4                    # 흑백에서도 4단계 전부 구분


def test_done_cancel_return_tiers_and_icons():
    d = _render("delivered", _KO["delivered"])
    assert _color_class(d) == "pc-lc-done" and "bi-check-circle" in d
    c = _render("canceled", _KO["canceled"])
    assert _color_class(c) == "pc-lc-cancel" and "bi-slash-circle" in c
    for s in ["returned", "exchanged", "refund_requested"]:
        r = _render(s, _KO[s])
        assert _color_class(r) == "pc-lc-return"             # 되돌림 = 전용 계층(≠danger)
        assert "bi-arrow-counterclockwise" in r              # 되돌림 아이콘(색약 1차 단서)


def test_return_tier_is_not_danger_red():
    # 되돌림 톤은 오류(danger 적색)와 분리 — CSS가 --danger가 아닌 --st-return 사용.
    css = Path("src/static/app.css").read_text(encoding="utf-8")
    assert "--st-return:" in css
    m = re.search(r"\.pc-lc-return\s*\{[^}]*\}", css)
    assert m and "--st-return" in m.group(0) and "--danger" not in m.group(0)


def test_grayscale_no_two_statuses_collapse():
    """색을 지운 뒤 9상태 비-색 서명이 전부 유일 — 흑백에서 의미 뭉갬 0."""
    sigs = [_noncolor_signature(_render(s, _KO[s])) for s in _ALL]
    assert len(set(sigs)) == len(_ALL)                       # 9개 전부 유일


def test_same_colorclass_groups_separated_by_noncolor_cue():
    # 같은 계층색 그룹 내에서도 비-색 단서로 구분되는지(색만으로 붙는 위험 제거).
    groups = {}
    for s in _ALL:
        html = _render(s, _KO[s])
        groups.setdefault(_color_class(html), []).append(_noncolor_signature(html))
    for cls, sigs in groups.items():
        assert len(set(sigs)) == len(sigs), f"{cls} 그룹이 색만으로 뭉갬"


# ── orders.html 배선 ─────────────────────────────────────────────────
def test_orders_uses_macro_no_bootstrap_color_badges():
    t = Path("src/seller_console/templates/orders.html").read_text(encoding="utf-8")
    assert 'from "_status_badge.html" import status_badge' in t
    assert "status_badge(o.status" in t
    # 부트스트랩 색 뱃지(status_colors bg-*·마켓 색)·bg-light 잔재 0.
    assert "badge bg-" not in t
    assert "status_colors" not in t


def test_orders_marketplace_is_muted():
    t = Path("src/seller_console/templates/orders.html").read_text(encoding="utf-8")
    # 마켓 = 뮤트 뱃지(라벨이 구분자) — bg-warning/success/danger 색코딩 제거.
    assert "pc-badge pc-badge-muted" in t
    assert "bg-warning text-dark" not in t and "bg-danger" not in t


def test_orders_page_renders_200():
    with app.test_client() as c:
        assert c.get("/seller/orders").status_code == 200

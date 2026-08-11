"""tests/test_v86_t_tokens_grade.py — v86-T: 토큰 관리 화면 상태뱃지 공통화 + 에디토리얼.

personal_tokens.html의 부트스트랩 badge bg-*(활성/삭제됨/스코프 태그) + 인라인 스타일 유휴만료를
공통 pc-badge(v86-P/R/S)로 통일 + 오버라인+금 헤어라인 헤더. 클린 상태 grade-up 마지막 화면.
"""
from __future__ import annotations

from pathlib import Path

TPL = Path("src/seller_console/templates/personal_tokens.html").read_text(encoding="utf-8")


def test_no_bootstrap_badges():
    for cls in ("badge bg-success", "badge bg-secondary", "badge bg-light", "badge bg-warning"):
        assert cls not in TPL, f"부트스트랩 badge 잔재: {cls}"


def test_status_badges_are_pc_badge():
    assert "pc-badge pc-badge-on" in TPL      # 활성
    assert "pc-badge pc-badge-off" in TPL     # 유휴 만료
    assert "pc-badge pc-badge-muted" in TPL   # 삭제됨 / 스코프 태그


def test_editorial_header():
    assert "console-kpi-label" in TPL and "pc-hairline" in TPL


def test_route_renders_and_no_regression(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    with app.test_client() as client:
        r = client.get("/seller/me/tokens")
        # 라우트 별칭에 따라 200 또는 리다이렉트(로그인/별칭) 허용 — 렌더 계약은 템플릿 asserts로.
        assert r.status_code in (200, 302)

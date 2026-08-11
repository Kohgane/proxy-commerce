"""tests/test_v86_s_markets_grade.py — v86-S: 고아 [Mock] 템플릿 제거 + 마켓 현황 상태뱃지 격상.

- market_status.html: 어느 라우트도 렌더하지 않는 고아 템플릿(하드코딩 [Mock] 가짜 데이터) 삭제
  (정직 데이터 — 코드베이스에 가짜 데이터 잔재 0).
- markets.html(라이브): 상품 상태 뱃지를 부트스트랩 badge bg-* → 공통 pc-badge(v86-P) + 원시
  price_anomaly → '가격 이상' + 금 헤어라인.
"""
from __future__ import annotations

from pathlib import Path

TPLDIR = Path("src/seller_console/templates")
SRC = Path("src/seller_console")
MARKETS = (TPLDIR / "markets.html").read_text(encoding="utf-8")


def test_orphan_mock_template_removed():
    assert not (TPLDIR / "market_status.html").exists(), "고아 [Mock] 템플릿이 아직 존재"
    # 어떤 코드도 그 템플릿을 렌더하지 않는다(주석 포함 잔재 0).
    for p in SRC.rglob("*.py"):
        if "__pycache__" in str(p):
            continue
        txt = p.read_text(encoding="utf-8")
        assert 'render_template("market_status.html"' not in txt
        assert "market_status.html" not in txt, f"{p}에 고아 템플릿 참조 잔재"


def test_no_mock_alo_yoga_fake_data_anywhere():
    # 하드코딩 [Mock] Alo Yoga 가짜 상품 데이터가 코드베이스에 없다.
    for p in TPLDIR.rglob("*.html"):
        assert "[Mock] Alo Yoga" not in p.read_text(encoding="utf-8"), f"{p}에 가짜 데이터 잔재"


def test_markets_item_state_badges_are_pc_badge():
    # 상품 상태 테이블 뱃지가 부트스트랩이 아니라 pc-badge.
    assert "pc-badge pc-badge-on" in MARKETS      # 활성
    assert "pc-badge pc-badge-danger" in MARKETS  # 오류
    assert "pc-badge pc-badge-muted" in MARKETS   # 정지/마켓라벨/미상
    # 상품 상태 분기의 부트스트랩 잔재 0(가격이상 bg-info 포함).
    for cls in ("badge bg-warning text-dark", "badge bg-info text-dark", "badge bg-danger"):
        assert cls not in MARKETS, f"부트스트랩 badge 잔재: {cls}"


def test_markets_price_anomaly_korean_label_and_hairline():
    assert "가격 이상" in MARKETS and "가격이상" not in MARKETS
    assert "pc-hairline" in MARKETS


def test_market_status_route_still_redirects(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    with app.test_client() as client:
        r = client.get("/seller/market-status")
        assert r.status_code in (301, 302)
        assert "/seller/markets" in r.headers.get("Location", "")

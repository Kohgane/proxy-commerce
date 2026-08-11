"""tests/test_v86_r_catalog_grade.py — v86-R: 상품 카탈로그 화면 에디토리얼 격상(STEP 5).

catalog.html/catalog_rows.html의 제네릭 h4 + 부트스트랩 badge bg-*(활성/품절/오류/정지) →
gogabridj 에디토리얼(오버라인+금 헤어라인) + 공통 상태 뱃지(pc-badge). 상태 필터 드롭다운의
원시 코드(active/out_of_stock/price_anomaly…)도 한글 라벨로.
"""
from __future__ import annotations

from pathlib import Path

CAT = Path("src/seller_console/templates/catalog.html").read_text(encoding="utf-8")
ROWS = Path("src/seller_console/templates/catalog_rows.html").read_text(encoding="utf-8")
APPCSS = Path("src/static/app.css").read_text(encoding="utf-8")


def test_editorial_header():
    assert "console-kpi-label" in CAT and "pc-hairline" in CAT


def test_status_badges_are_pc_badge_not_bootstrap():
    for cls in ("badge bg-success", "badge bg-warning", "badge bg-danger",
                "badge bg-secondary", "badge bg-dark", "badge bg-light"):
        assert cls not in ROWS, f"부트스트랩 badge 잔재: {cls}"
    # 상태별 gogabridj 뱃지 변형.
    assert "pc-badge pc-badge-on" in ROWS      # 활성
    assert "pc-badge pc-badge-off" in ROWS     # 품절/가격이상/준비중
    assert "pc-badge pc-badge-danger" in ROWS  # 오류
    assert "pc-badge pc-badge-muted" in ROWS   # 정지/마켓 라벨


def test_price_anomaly_has_korean_label_not_raw_code():
    # price_anomaly 상태가 원시 코드가 아니라 '가격 이상'으로 표시.
    assert "가격 이상" in ROWS
    assert "'price_anomaly'" in ROWS  # 분기 조건은 코드, 표시는 한글


def test_state_filter_dropdown_uses_korean_labels():
    # 상태 필터 옵션이 원시 코드 대신 한글 라벨 맵을 쓴다.
    assert "_state_labels" in CAT
    for label in ("활성", "품절", "오류", "가격 이상", "정지"):
        assert label in CAT, f"상태 한글 라벨 누락: {label}"
    # 원시 코드를 그대로 옵션 텍스트로 출력하지 않는다.
    assert "{{ st }}</option>" not in CAT


def test_pc_badge_muted_token_added():
    assert ".pc-badge-muted" in APPCSS
    i = APPCSS.find(".pc-badge-muted")
    assert "var(--text-muted" in APPCSS[i:i + 240], "muted 뱃지가 토큰(--text-muted) 미사용"


def test_catalog_rows_preserve_card_contract():
    # v36 카드화 계약(모바일) 보존.
    for lbl in ('data-label="SKU"', 'data-label="가격"', 'data-label="상태"'):
        assert lbl in ROWS
    assert "cardcell-title" in ROWS and "cardcell-actions" in ROWS and "cardcell-img" in ROWS

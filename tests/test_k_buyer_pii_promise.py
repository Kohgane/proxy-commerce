"""tests/test_k_buyer_pii_promise.py — **대외 약속 방어**: 구매자 PII 미보관.

카카오 연동대행사 검토요청(2026-09-02 제출)에서 Q11 "별도 저장하지 않음",
Q12 "실시간 조회만 · 로그에 PII 미기록"으로 답했고, 소개서 4장에도 같은 내용이 실렸다.
**제출된 약속**이라 코드가 그 방향에서 벗어나면 대외 신뢰 문제가 된다.

**실측(2026-09-02)으로 확인한 현재 상태 — 이 계약이 지키는 선:**
  · 주문 저장 스키마에 **원문 buyer 컬럼 0**. 있는 건 `*_masked` 셋뿐이다.
  · 모델도 마스킹 필드만 들고 있다(원문을 담을 자리가 없다).
  · 저장 시 그 마스킹 값만 쓴다.

즉 "원문 미보관"은 사실이고, 저장되는 것은 **마스킹된 최소 표시값**이다.
이 계약은 그 선이 뒤로 밀리는 것(원문 컬럼 추가·원문 로깅)을 막는다.
설계를 바꿔야 하면 **오너 게이트**다 — 지뢰 「구매자 PII 미보관 대외약속」 참조.
"""
from __future__ import annotations

import re
from pathlib import Path

SCHEMA = Path("src/db/schema_stage3.sql")
MODELS = Path("src/seller_console/orders/models.py")
ADAPTER = Path("src/seller_console/orders/sheets_adapter.py")
ORDERS_PG = Path("src/db/orders_pg.py")

# 원문 PII로 볼 컬럼/필드 이름(마스킹 접미가 없는 것).
_RAW_BUYER_RE = re.compile(
    r"\b(buyer_(?:name|phone|tel|mobile|address|addr|email)|receiver_(?:name|phone|address)|"
    r"recipient_(?:name|phone|address))\b(?!_masked)")


def _code_only(path: Path) -> str:
    """주석·독스트링 제외 — 근거를 문서에 인용했다고 계약이 깨지면 안 된다."""
    src = path.read_text(encoding="utf-8")
    src = re.sub(r'""".*?"""', "", src, flags=re.S)
    return "\n".join(l for l in src.splitlines()
                     if not l.lstrip().startswith(("#", "--")))


def test_orders_schema_has_no_raw_buyer_columns():
    """★ 주문 테이블에 **원문 구매자 컬럼이 없다**. 있는 건 마스킹 셋뿐."""
    ddl = _code_only(SCHEMA)
    leaked = _RAW_BUYER_RE.findall(ddl)
    assert not leaked, f"원문 구매자 컬럼: {leaked}"
    for col in ("buyer_name_masked", "buyer_phone_masked", "buyer_address_masked"):
        assert col in ddl, col


def test_order_model_cannot_hold_raw_pii():
    """모델에 원문을 담을 자리가 없다 — 담을 곳이 없으면 새어 나갈 곳도 없다."""
    code = _code_only(MODELS)
    assert not _RAW_BUYER_RE.findall(code)
    for f in ("buyer_name_masked", "buyer_phone_masked", "buyer_address_masked"):
        assert f in code, f


def test_persist_paths_write_masked_values_only():
    """저장 경로(시트·PG)가 쓰는 값은 마스킹 필드뿐이다."""
    for path in (ADAPTER, ORDERS_PG):
        code = _code_only(path)
        assert not _RAW_BUYER_RE.findall(code), path


def test_masking_actually_masks():
    """마스킹이 실제로 가린다 — 이름·전화·주소 각각."""
    from src.seller_console.orders.models import mask_address, mask_name, mask_phone
    assert mask_name("홍길동") == "홍*동"
    assert mask_phone("010-1234-5678") == "010-****-5678"
    masked_addr = mask_address("서울특별시 강남구 테헤란로 123 4층")
    assert "테헤란로" not in masked_addr and masked_addr.endswith("***")


def test_pii_is_not_logged():
    """★ Q12 — 로그에 구매자 정보를 찍지 않는다(마스킹 값조차 로그로 흘리지 않는다)."""
    for path in (ADAPTER, ORDERS_PG, MODELS):
        for line in _code_only(path).splitlines():
            if "logger." in line or "print(" in line:
                assert "buyer" not in line.lower(), f"{path}: {line.strip()}"

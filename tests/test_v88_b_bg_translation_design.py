"""tests/test_v88_b_bg_translation_design.py — v88-B: 백그라운드 번역 설계 문서 완비 계약.

설계 트랙(코드 최소). 이 계약은 설계 문서가 오너 명세 섹션을 전부 담고, **불변 원칙(체인·캡·쿼터 무손대)**을
명시하는지 못박는다. 구현은 승인 후 별 트랙 — 이 테스트는 문서 존재/완비만 검증(런타임 코드 계약 아님).
"""
from __future__ import annotations

from pathlib import Path

DOC = Path("docs/design/background-translation.md")
TXT = DOC.read_text(encoding="utf-8") if DOC.exists() else ""


def test_design_doc_exists():
    assert TXT.strip(), "docs/design/background-translation.md 없음/빈 문서"


def test_covers_owner_spec_sections():
    # 오너 명세: 작업 저장소·상태 전이·폴링 계약·벌크·재시도 정책.
    for kw in ["작업 저장소", "상태 전이", "폴링", "벌크", "재시도"]:
        assert kw in TXT, ("설계 섹션 누락", kw)
    # 상태 4종.
    for st in ["pending", "running", "success", "failed"]:
        assert st in TXT, ("상태 누락", st)
    # 폴링 계약 엔드포인트.
    assert "enqueue" in TXT and "status" in TXT


def test_reuses_existing_conventions_not_reinvent():
    # 기존 관례 재사용 우선 — 명시.
    for asset in ["queue_manager", "schema_stage", "SKIP LOCKED", "translation_usage", "pg.py", "W7a"]:
        assert asset in TXT, ("재사용 자산 미참조", asset)


def test_invariants_stated_chain_cap_quota_untouched():
    # 금지: 체인·캡·쿼터 무손대 — 문서가 명시적으로 못박아야 한다.
    assert "무손대" in TXT
    assert "W10" in TXT and ("캡 유지" in TXT or "캡은 유지" in TXT)   # 요청 예산 캡 유지(이중 안전망)
    assert "쿼터 회계" in TXT and "쿼터" in TXT
    # 폴백 정직: PG 미가동 시 동기 경로+캡(무회귀).
    assert "무회귀" in TXT or "폴백" in TXT


def test_implementation_wired():
    # v88-B 구현 승인("전부 가라") — 설계가 구현으로 배선됨(schema_stage5 + 워커 + 라우트).
    assert Path("src/db/schema_stage5.sql").exists(), "구현 스키마 미배선"
    assert Path("src/db/translation_jobs_pg.py").exists()
    assert Path("src/seller_console/translate_worker.py").exists()
    assert "구현 완료" in TXT, "설계 문서에 구현 완료 상태 미표기"

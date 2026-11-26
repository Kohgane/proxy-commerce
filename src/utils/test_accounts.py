"""Y12-D(오너 2026-10-18) — 시험 계정은 운영 집계에 섞지 않는다.

`QA-TEST-…`(영속성 실증 마커 · QA 시험 주문) · `dev`(개발 세션) 계정의 수집 행은 지우지 않는다 — 그 계정으로 들어가면
그대로 보인다. 다만 **셀러를 정하지 않은 전체 집계**(진단 소싱 큐 · 공개 통계 · 관리자 표 · 일회성 백필)에선 뺀다.
판정은 이 한 곳(`is_test_account` · SQL 조각 `NOT_TEST_SQL`) — 집계마다 다시 적지 않는다.
"""
from __future__ import annotations

TEST_ACCOUNT_PREFIXES = ("QA-TEST",)
TEST_ACCOUNT_IDS = (
    "dev",
    # 순찰 95(오너 2026-10-25): 중국 접속 실측용 시험 계정 kgp-cn-test-1025@example.com(10-24 가입) — 그 상품 cd7429ff도 같이 빠진다
    "a07afb1b-72f9-4127-a0e9-682ed13aab39",
)

#: `user_id` 열이 있는 표에 붙이는 조건(인자 없는 쿼리·있는 쿼리 둘 다 — `%%`는 LIKE에서 와일드카드 둘이라 같은 뜻)
NOT_TEST_SQL = ("NOT (COALESCE(user_id, '') LIKE 'QA-TEST%%' OR COALESCE(user_id, '') IN ("
                + ", ".join(f"'{i}'" for i in TEST_ACCOUNT_IDS) + "))")


def is_test_account(user_id) -> bool:
    u = str(user_id or "")
    return u in TEST_ACCOUNT_IDS or any(u.startswith(p) for p in TEST_ACCOUNT_PREFIXES)


# ── 오너 11-26 감독 3d: 앱스토어 **심사용 계정** — 둘러보기·수집·편집·사전검증은 되고, 마켓으로 보내는 일은 막는다 ──────────
#   누가 심사 계정인지는 env(`REVIEW_ACCOUNT_EMAILS`·`REVIEW_ACCOUNT_IDS`, 쉼표) — 값 넣기는 오너(env 변경).
REVIEW_BLOCK_MESSAGE = "심사용 둘러보기 계정이라 마켓으로 보내지 않아요 — 수집·편집·사전검증까지는 그대로 써 보실 수 있어요."


def _env_set(name: str) -> set:
    import os
    return {x.strip().lower() for x in str(os.getenv(name, "") or "").split(",") if x.strip()}


def is_review_account(user_id="", email="") -> bool:
    ids, emails = _env_set("REVIEW_ACCOUNT_IDS"), _env_set("REVIEW_ACCOUNT_EMAILS")
    return bool((user_id and str(user_id).strip().lower() in ids) or (email and str(email).strip().lower() in emails))


def review_session() -> bool:
    """지금 요청의 로그인 세션이 심사 계정인가(요청 밖이면 False)."""
    try:
        from flask import has_request_context, session
        if not has_request_context():
            return False
        return is_review_account(session.get("user_id") or "", session.get("email") or "")
    except Exception:                                    # noqa: BLE001
        return False

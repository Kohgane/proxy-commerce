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

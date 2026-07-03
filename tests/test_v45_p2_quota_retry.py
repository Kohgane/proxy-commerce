"""tests/test_v45_p2_quota_retry.py — v45 P2: 수집 성공률 들쭉날쭉(★쿼터 지목).

원인: Sheets 분당 쿼터(429)를 삼키고 폴백/성공 처리 → 전송된 수집이 비영속(durable=False)으로
502되며 '가끔 실패'. 수리: 시트 write 직렬화 + 429/5xx 지수 백오프 재시도(최대 3회) → 전이적
429는 재시도로 회복(성공률 안정), 끝까지 실패는 정직 실패. 429/5xx 카운트 로깅.

이 가드:
 ①append: 첫 시도 429 → 재시도로 성공 → durable=True(수집 성공 회복), 429 카운트 증가.
 ②append: 영속 429 → tries 소진 → durable=False(인메모리 폴백, 정직 실패).
 ③재시도 불가(403 권한)는 즉시 실패(재시도 낭비 0).
 ④delete batchUpdate도 429 재시도로 회복.
 ⑤16건 반복 수집: 매 시도 첫 429여도 전건 durable 저장(성공+실패=16, 성공분 실존).
"""
from __future__ import annotations

import pytest


class _Resp:
    def __init__(self, code):
        self.status_code = code


class _APIErr(Exception):
    def __init__(self, code):
        super().__init__(f"HTTP {code}")
        self.response = _Resp(code)


class _FakeWS:
    """append/batch_update 시 정해진 횟수만큼 429를 낸 뒤 성공하는 가짜 워크시트."""
    header = [
        "id", "collected_at", "source", "domain", "url", "title",
        "image_url", "price", "currency", "status", "preview_url", "extra_json", "seller_id",
    ]

    def __init__(self, fail_times=0, fail_code=429, fail_forever=False):
        self.rows = []
        self.fail_times = fail_times
        self.fail_code = fail_code
        self.fail_forever = fail_forever
        self._calls = 0
        self.id = 1
        self.spreadsheet = self

    def row_values(self, index):
        return list(self.header) if index == 1 else []

    def get_all_records(self):
        return [dict(zip(self.header, r)) for r in self.rows]

    def get_all_values(self):
        return [list(self.header)] + [list(r) for r in self.rows]

    def append_row(self, row):
        self._calls += 1
        if self.fail_forever or self._calls <= self.fail_times:
            raise _APIErr(self.fail_code)
        self.rows.append(list(row))

    def batch_update(self, body):
        self._calls += 1
        if self.fail_forever or self._calls <= self.fail_times:
            raise _APIErr(self.fail_code)
        drop = set()
        for req in body.get("requests", []):
            rng = req["deleteDimension"]["range"]
            for zero in range(rng["startIndex"], rng["endIndex"]):
                drop.add(zero - 1)
        self.rows = [r for i, r in enumerate(self.rows) if i not in drop]


@pytest.fixture
def store(monkeypatch):
    from src.seller_console import collect_history_store as st
    st._in_memory[:] = []
    st._quota_stats.update(count_429=0, count_5xx=0, retries=0)
    monkeypatch.setattr(st, "_SHEET_ID", "sheet-test", raising=False)
    monkeypatch.setattr(st.time, "sleep", lambda *_a, **_k: None)   # 테스트 가속
    return st


def test_append_retries_429_then_durable(store):
    ws = _FakeWS(fail_times=1)   # 첫 시도 429 → 재시도 성공
    store._get_worksheet = lambda: ws
    iid, durable = store.append(source="extension", url="https://x.com/p",
                                title="t", seller_id="u1", return_durable=True)
    assert iid and durable is True                     # 재시도로 성공 회복
    assert store.get_quota_stats()["count_429"] == 1   # 429 관측 카운트
    assert store.get_quota_stats()["retries"] >= 1
    assert store.existing_ids([iid], seller_ids={"u1"}) == {iid}   # 시트에 실존


def test_append_persistent_429_is_honest_failure(store):
    ws = _FakeWS(fail_forever=True)   # 계속 429 → tries 소진
    store._get_worksheet = lambda: ws
    iid, durable = store.append(source="extension", url="https://x.com/p",
                                title="t", seller_id="u1", return_durable=True)
    assert durable is False            # 정직 실패(인메모리 폴백) — 엔드포인트가 502
    assert store.get_quota_stats()["count_429"] == 3   # 3회 시도 전부 429


def test_non_retryable_403_fails_fast(store):
    ws = _FakeWS(fail_forever=True, fail_code=403)   # 권한 오류 = 재시도 안 함
    store._get_worksheet = lambda: ws
    _iid, durable = store.append(source="extension", url="https://x.com/p",
                                 title="t", seller_id="u1", return_durable=True)
    assert durable is False
    assert store.get_quota_stats()["count_429"] == 0   # 재시도 낭비 0
    assert ws._calls == 1                              # 단 1회 시도 후 즉시 실패


def test_delete_batchupdate_retries_429(store):
    ws = _FakeWS(fail_times=0)
    store._get_worksheet = lambda: ws
    ids = [store.append(source="extension", url=f"https://x.com/{k}", title=f"t{k}",
                        seller_id="u1", return_durable=False) for k in range(3)]
    # 삭제 batchUpdate 첫 시도 429 유도
    ws.fail_times, ws._calls = 1, 0
    removed = store.delete_ids(ids, seller_ids={"u1"})
    assert set(removed) == set(ids)                     # 재시도로 전건 삭제 회복
    assert store.get_quota_stats()["count_429"] == 1


def test_16_bulk_collect_all_durable_despite_429(store):
    """판정: 16건 수집, 매 append 첫 시도 429여도 전건 durable 저장(성공분 실존)."""
    ws = _FakeWS(fail_times=0)
    store._get_worksheet = lambda: ws
    ok = 0
    ids = []
    for k in range(16):
        ws.fail_times, ws._calls = 1, 0   # 매 append 첫 시도만 429
        iid, durable = store.append(source="bulk", url=f"https://x.com/g{k}",
                                    title=f"상품{k}", seller_id="u1", return_durable=True)
        if durable:
            ok += 1
            ids.append(iid)
    assert ok == 16                                      # 성공+실패 합계 16, 실패 0
    present = store.existing_ids(ids, seller_ids={"u1"})
    assert present == set(ids)                           # 성공분 전부 이력 실존
    assert store.get_quota_stats()["count_429"] == 16    # 매회 429 1번씩 관측·회복

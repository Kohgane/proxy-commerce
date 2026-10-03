"""Y4(오너 2026-10-04) — 이미지 번역 차단기 오작동: 「그릴 줄이 없습니다(원본 그대로)」는 실패가 아니다.

실측(운영 큐, 09-30 12:15:40Z 재개 뒤 실패 20장 = 차단): 그릴 줄 없음 12 · Tencent 「无文本图片」 2 → **글자 없는 사진 14** ·
진짜 실패 6(「输入Data无效」 3 · 내려받기 ValueError 2 · 응답에 번역 이미지 없음 1). 대기 272장.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.db import image_translate_queue_pg as Q
from src.services import image_translate_auto as A

REASONS = (["그릴 줄이 없습니다(원본 그대로)"] * 12 + ["翻译失败，输入为无文本图片。"] * 2
           + ["输入Data无效，请参考Data参数说明。"] * 3 + ["이미지를 내려받지 못했습니다(ValueError)"] * 2
           + ["응답에 번역 이미지가 없습니다"])


@pytest.fixture
def mem_queue(monkeypatch):
    monkeypatch.setattr(Q, "_enabled", lambda: False)
    saved = list(Q._MEM_Q)
    Q._MEM_Q.clear()
    yield
    Q._MEM_Q.clear()
    Q._MEM_Q.extend(saved)


def _fill(reasons):
    Q.enqueue("u-y4", "item-y4", [("gallery", i) for i in range(len(reasons))])
    for r, why in zip([r for r in Q._MEM_Q if r["item_id"] == "item-y4"], reasons):
        Q.finish(r["id"], "failed", why)


def test_breaker_counts_only_real_failures(mem_queue):
    _fill(REASONS)
    since = datetime.now(timezone.utc) - timedelta(minutes=5)
    assert Q.failed_since(since) == 6
    bd = Q.failure_breakdown(since)
    assert sum(n for _r, n, nt in bd if nt) == 14 and sum(n for _r, n, nt in bd if not nt) == 6


def test_no_text_result_is_skipped_not_failed(mem_queue, monkeypatch):
    from src.seller_console import collect_history_store as S
    iid = S.append(source="extension", url="https://item.taobao.com/item.htm?id=1", seller_id="u-y4",
                   title="x", price="1", currency="CNY", extra={"images": ["https://img.alicdn.com/a.jpg"]})
    monkeypatch.setattr(A, "translate_page", lambda *a, **k: {"idx": 0, "kind": "gallery", "status": "failed",
                                                              "error_message": "그릴 줄이 없습니다(원본 그대로)"})
    st, why = A._translate_job({"item_id": iid, "kind": "gallery", "idx": 0, "user_id": "u-y4"})
    assert st == "skipped" and why.startswith("글자 없는 사진 — 원본 그대로")


def test_heal_breaker_resumes_only_when_real_failures_are_below_cap(mem_queue, monkeypatch):
    started = []
    monkeypatch.setattr(A, "kick", lambda: started.append(1))
    long_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    Q.state_set(A._STATE_KEY, {"paused": True, "reason": "번역 실패 20장 누적 — …(마지막 사유: 그릴 줄이 없습니다)",
                               "resumed_at": long_ago})
    _fill(REASONS)
    r = A.heal_breaker()
    assert r["healed"] and r["real_failed"] == 6 and not A.pause_state().get("paused") and started
    # 진짜 실패가 상한 이상이면 그대로
    Q.state_set(A._STATE_KEY, {"paused": True, "reason": "번역 실패 20장 누적", "resumed_at": long_ago})
    _fill(["输入Data无效"] * 20)
    assert A.heal_breaker()["healed"] is False and A.pause_state()["paused"]
    # 사람이 멈춘 것은 건드리지 않는다
    Q.state_set(A._STATE_KEY, {"paused": True, "reason": "오너가 멈춤", "resumed_at": long_ago})
    assert A.heal_breaker()["healed"] is False
    Q.state_set(A._STATE_KEY, {})

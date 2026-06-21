"""tests/test_sheet_read_cache.py — v8 속도: 요청 범위 시트 read 캐시 (Phase 264)."""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class _FakeWS:
    def __init__(self):
        self.reads = 0

    def get_all_records(self):
        self.reads += 1
        return [{"id": "a", "collected_at": "2026-06-20T00:00:00+00:00",
                 "domain": "x", "source": "manual", "seller_id": "s1", "title": "t"}]


def test_request_scoped_cache_dedupes_reads():
    """같은 요청 안에서 list+list+get = 시트 read 1회(중복 제거)."""
    from src.seller_console import collect_history_store as chs
    from src.order_webhook import app
    ws = _FakeWS()
    with patch.object(chs, "_SHEET_ID", "sheet-x"), patch.object(chs, "_get_worksheet", return_value=ws):
        with app.test_request_context("/seller/collect/history"):
            from flask import g
            if hasattr(g, "_kgp_ch_rows"): delattr(g, "_kgp_ch_rows")
            chs.list_items(seller_id="s1")
            chs.list_items(seller_id="s1", days=7)
            chs.get("a", seller_id="s1")
    assert ws.reads == 1


def test_cache_invalidated_after_write():
    """쓰기(update) 후 같은 요청 내 read가 최신을 다시 읽는다(스테일 방지)."""
    from src.seller_console import collect_history_store as chs
    from src.order_webhook import app
    ws = _FakeWS()
    # update는 get_all_values를 쓰므로 read 카운트와 무관 — 캐시 무효화만 확인.
    ws.get_all_values = lambda: [["id", "seller_id", "title"], ["a", "s1", "t"]]
    ws.update_cell = lambda *a, **k: None
    ws.row_values = lambda *a, **k: ["id", "seller_id", "title"]
    with patch.object(chs, "_SHEET_ID", "sheet-x"), patch.object(chs, "_get_worksheet", return_value=ws):
        with app.test_request_context("/x"):
            from flask import g
            if hasattr(g, "_kgp_ch_rows"): delattr(g, "_kgp_ch_rows")
            chs.list_items(seller_id="s1")          # read 1 (캐시 채움)
            chs.update("a", seller_id="s1", title="new")  # 무효화
            chs.get("a", seller_id="s1")            # read 2 (캐시 비었으므로 재read)
    assert ws.reads == 2

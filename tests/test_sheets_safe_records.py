import os
import sys
from unittest.mock import patch

import gspread

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.inventory.inventory_sync import InventorySync  # noqa: E402
from src.utils.sheets import get_all_records_safe  # noqa: E402


class FakeWorksheet:
    def __init__(self, records=None, values=None, error=None, title='catalog'):
        self._records = list(records or [])
        self._values = list(values or [])
        self._error = error
        self.title = title
        self.expected_headers_seen = None

    def get_all_records(self, expected_headers=None):
        self.expected_headers_seen = expected_headers
        if self._error is not None:
            raise self._error
        return list(self._records)

    def get_all_values(self):
        return [list(row) for row in self._values]


def test_get_all_records_safe_returns_native_records():
    ws = FakeWorksheet(records=[{'sku': 'SKU-1', 'price': '1000'}])

    result = get_all_records_safe(ws)

    assert result == [{'sku': 'SKU-1', 'price': '1000'}]
    assert ws.expected_headers_seen is None


def test_get_all_records_safe_forwards_expected_headers():
    ws = FakeWorksheet(records=[{'sku': 'SKU-1'}])

    result = get_all_records_safe(ws, expected_headers=['sku'])

    assert result == [{'sku': 'SKU-1'}]
    assert ws.expected_headers_seen == ['sku']


def test_get_all_records_safe_dedupes_blank_headers():
    ws = FakeWorksheet(
        values=[
            ['sku', '', '', 'price'],
            ['SKU-1', 'extra-a', 'extra-b', '1000'],
        ],
        error=ValueError("the header row in the worksheet is not unique"),
    )

    result = get_all_records_safe(ws)

    assert result == [{
        'sku': 'SKU-1',
        'col_2': 'extra-a',
        'col_3': 'extra-b',
        'price': '1000',
    }]


def test_get_all_records_safe_dedupes_named_headers():
    ws = FakeWorksheet(
        values=[
            ['sku', 'name', 'name'],
            ['SKU-1', 'alpha', 'beta'],
        ],
        error=ValueError("header row not unique"),
    )

    result = get_all_records_safe(ws)

    assert result == [{'sku': 'SKU-1', 'name': 'alpha', 'name_2': 'beta'}]


def test_get_all_records_safe_falls_back_on_gspread_header_error(caplog):
    ws = FakeWorksheet(
        values=[
            ['sku', 'status', 'src_url'],
            ['SKU-1', 'active', 'https://example.com/a'],
        ],
        error=gspread.exceptions.GSpreadException("header row is not unique"),
        title='catalog',
    )

    with caplog.at_level('WARNING'):
        result = get_all_records_safe(ws)

    assert result == [{
        'sku': 'SKU-1',
        'status': 'active',
        'src_url': 'https://example.com/a',
    }]
    assert 'worksheet=catalog' in caplog.text


def test_get_all_records_safe_returns_empty_list_for_empty_sheet():
    ws = FakeWorksheet(
        values=[],
        error=ValueError("the header row in the worksheet is not unique"),
    )

    assert get_all_records_safe(ws) == []


def test_get_all_records_safe_returns_empty_list_for_blank_header_row():
    ws = FakeWorksheet(
        values=[['', '   '], ['SKU-1', 'value']],
        error=ValueError("the header row in the worksheet is not unique"),
    )

    assert get_all_records_safe(ws) == []


def test_inventory_sync_get_active_rows_handles_duplicate_headers():
    ws = FakeWorksheet(
        values=[
            ['sku', 'status', '', 'src_url', 'vendor'],
            ['SKU-1', 'active', 'memo', 'https://example.com/a', 'porter'],
            ['SKU-2', 'inactive', 'memo', 'https://example.com/b', 'porter'],
            ['SKU-3', 'active', 'memo', '', 'porter'],
        ],
        error=ValueError("the header row in the worksheet is not unique"),
    )
    sync = InventorySync(sheet_id='fake-sheet', worksheet='catalog')

    with patch('src.inventory.inventory_sync.open_sheet', return_value=ws):
        rows = sync._get_active_rows()

    assert rows == [{
        'sku': 'SKU-1',
        'status': 'active',
        'col_3': 'memo',
        'src_url': 'https://example.com/a',
        'vendor': 'porter',
    }]

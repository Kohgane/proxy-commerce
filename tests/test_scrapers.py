"""
tests/test_scrapers.py
src/scrapers 모듈 단위 테스트
"""

import io
import json
import os
import sys
import tempfile
from unittest.mock import MagicMock, patch, call

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.scrapers.listly_client import ListlyLoader

# 샘플 파일 경로
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
PORTER_SAMPLE = os.path.join(DATA_DIR, 'porter_raw_sample.csv')
MEMO_SAMPLE = os.path.join(DATA_DIR, 'memo_raw_sample.csv')


# ──────────────────────────────────────────────────────────────────────────────
# ListlyLoader 테스트
# ──────────────────────────────────────────────────────────────────────────────

class TestListlyLoadCsv:
    """test_listly_load_csv: CSV 로드 테스트 (샘플 파일 사용)"""

    def test_load_porter_csv(self):
        loader = ListlyLoader()
        rows = loader.load_csv(PORTER_SAMPLE)
        assert len(rows) == 5
        assert 'product_name' in rows[0]
        assert 'price' in rows[0]
        assert 'url' in rows[0]

    def test_load_memo_csv(self):
        loader = ListlyLoader()
        rows = loader.load_csv(MEMO_SAMPLE)
        assert len(rows) == 4
        assert 'product_name' in rows[0]
        assert 'collection' in rows[0]

    def test_load_csv_file_not_found(self):
        loader = ListlyLoader()
        with pytest.raises(FileNotFoundError):
            loader.load_csv('/nonexistent/path.csv')

    def test_load_csv_returns_list_of_dicts(self):
        loader = ListlyLoader()
        rows = loader.load_csv(PORTER_SAMPLE)
        assert all(isinstance(r, dict) for r in rows)

    def test_load_csv_with_temp_file(self):
        csv_content = 'name,price\nProduct A,¥1000\nProduct B,¥2000\n'
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write(csv_content)
            tmp_path = f.name
        try:
            loader = ListlyLoader()
            rows = loader.load_csv(tmp_path)
            assert len(rows) == 2
            assert rows[0]['name'] == 'Product A'
        finally:
            os.unlink(tmp_path)


class TestListlyLoadJson:
    """test_listly_load_json: JSON 로드 테스트"""

    def test_load_json_list(self):
        data = [
            {'product_name': 'Bag A', 'price': '¥10000', 'url': 'http://example.com/1'},
            {'product_name': 'Bag B', 'price': '¥20000', 'url': 'http://example.com/2'},
        ]
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            json.dump(data, f)
            tmp_path = f.name
        try:
            loader = ListlyLoader()
            rows = loader.load_json(tmp_path)
            assert len(rows) == 2
            assert rows[0]['product_name'] == 'Bag A'
        finally:
            os.unlink(tmp_path)

    def test_load_json_items_wrapper(self):
        """{'items': [...]} 형태 지원"""
        data = {'items': [{'name': 'X', 'price': '€100'}]}
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            json.dump(data, f)
            tmp_path = f.name
        try:
            loader = ListlyLoader()
            rows = loader.load_json(tmp_path)
            assert len(rows) == 1
            assert rows[0]['name'] == 'X'
        finally:
            os.unlink(tmp_path)

    def test_load_json_invalid_format(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            f.write('not valid json {{{')
            tmp_path = f.name
        try:
            loader = ListlyLoader()
            with pytest.raises(ValueError, match='JSON 형식 오류'):
                loader.load_json(tmp_path)
        finally:
            os.unlink(tmp_path)

    def test_load_json_file_not_found(self):
        loader = ListlyLoader()
        with pytest.raises(FileNotFoundError):
            loader.load_json('/nonexistent/path.json')


class TestListlyCleanRawData:
    """test_listly_clean_raw_data: 빈 행 제거, 트림 테스트"""

    def test_removes_empty_rows(self):
        loader = ListlyLoader()
        rows = [
            {'name': 'Product A', 'price': '¥1000'},
            {'name': '', 'price': ''},
            {'name': 'Product B', 'price': '¥2000'},
        ]
        cleaned = loader.clean_raw_data(rows)
        assert len(cleaned) == 2

    def test_trims_whitespace(self):
        loader = ListlyLoader()
        rows = [{'name': '  Product A  ', 'price': ' ¥1000 '}]
        cleaned = loader.clean_raw_data(rows)
        assert cleaned[0]['name'] == 'Product A'
        assert cleaned[0]['price'] == '¥1000'

    def test_removes_all_empty_dict(self):
        loader = ListlyLoader()
        rows = [{'a': '', 'b': '', 'c': ''}]
        cleaned = loader.clean_raw_data(rows)
        assert len(cleaned) == 0

    def test_skips_non_dict(self):
        loader = ListlyLoader()
        rows = [{'name': 'A'}, 'not a dict', None, {'name': 'B'}]
        cleaned = loader.clean_raw_data(rows)
        assert len(cleaned) == 2

    def test_preserves_count(self):
        loader = ListlyLoader()
        rows = loader.load_csv(PORTER_SAMPLE)
        cleaned = loader.clean_raw_data(rows)
        assert len(cleaned) == 5  # 샘플에는 빈 행이 없음


class TestListlyEncodingFallback:
    """test_listly_encoding_fallback: 인코딩 폴백 테스트"""

    def test_utf8_sig_bom(self):
        """UTF-8 BOM 파일 처리."""
        content = 'name,price\nProduct,¥1000\n'
        raw = content.encode('utf-8-sig')
        with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as f:
            f.write(raw)
            tmp_path = f.name
        try:
            loader = ListlyLoader()
            rows = loader.load_csv(tmp_path)
            assert len(rows) == 1
            assert rows[0]['name'] == 'Product'
        finally:
            os.unlink(tmp_path)

    def test_euc_kr_fallback(self):
        """EUC-KR 인코딩 폴백."""
        content = 'name,price\n가방,10000\n'
        raw = content.encode('euc-kr')
        with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as f:
            f.write(raw)
            tmp_path = f.name
        try:
            loader = ListlyLoader()
            rows = loader.load_csv(tmp_path)
            assert len(rows) == 1
        finally:
            os.unlink(tmp_path)

    def test_unknown_encoding_raises(self):
        """모든 인코딩으로 읽을 수 없으면 ValueError."""
        raw = bytes([0xFF, 0xFE, 0x00, 0x01, 0xFF, 0x00])
        with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as f:
            f.write(raw)
            tmp_path = f.name
        try:
            loader = ListlyLoader()
            with pytest.raises((ValueError, UnicodeDecodeError)):
                loader.load_csv(tmp_path)
        finally:
            os.unlink(tmp_path)


# ──────────────────────────────────────────────────────────────────────────────
# SheetImporter 테스트 (Google Sheets는 mock 처리)
# ──────────────────────────────────────────────────────────────────────────────

def _make_mock_ws(existing_records=None):
    """gspread Worksheet mock 생성 헬퍼."""
    ws = MagicMock()
    ws.get_all_records.return_value = existing_records or []
    ws.append_rows.return_value = None
    ws.update_cell.return_value = None
    return ws


def _make_importer(mock_ws):
    """SheetImporter를 open_sheet mock과 함께 생성."""
    with patch('src.scrapers.sheet_importer.open_sheet', return_value=mock_ws):
        from src.scrapers.sheet_importer import SheetImporter
        return SheetImporter(sheet_id='test-sheet-id', worksheet_name='catalog')


class TestSheetImporterGetExistingSkus:
    """test_sheet_importer_get_existing_skus: 기존 SKU 조회 (mock)"""

    def test_returns_set_of_skus(self):
        records = [
            {'sku': 'PORT-001', 'title_ko': '상품A'},
            {'sku': 'PORT-002', 'title_ko': '상품B'},
        ]
        ws = _make_mock_ws(records)
        importer = _make_importer(ws)
        skus = importer.get_existing_skus()
        assert skus == {'PORT-001', 'PORT-002'}

    def test_empty_sheet_returns_empty_set(self):
        ws = _make_mock_ws([])
        importer = _make_importer(ws)
        skus = importer.get_existing_skus()
        assert skus == set()

    def test_ignores_rows_without_sku(self):
        records = [
            {'sku': 'PORT-001', 'title_ko': '상품A'},
            {'sku': '', 'title_ko': '상품B'},
            {'title_ko': '상품C'},
        ]
        ws = _make_mock_ws(records)
        importer = _make_importer(ws)
        skus = importer.get_existing_skus()
        assert skus == {'PORT-001'}


class TestSheetImporterUpsertNew:
    """test_sheet_importer_upsert_new: 신규 행 추가 테스트 (mock)"""

    def test_new_rows_are_appended(self):
        ws = _make_mock_ws([])
        importer = _make_importer(ws)
        rows = [
            {'sku': 'PORT-NEW1', 'title_ko': '새상품1', 'buy_currency': 'JPY',
             'buy_price': '10000', 'vendor': 'porter', 'status': 'active',
             'title_en': '', 'title_ja': '新商品1', 'title_fr': '',
             'src_url': 'http://example.com/1', 'source_country': 'JP',
             'images': '', 'stock': 0, 'tags': ''},
        ]
        result = importer.upsert_rows(rows)
        assert result['added'] == 1
        assert result['updated'] == 0
        ws.append_rows.assert_called_once()

    def test_returns_correct_count(self):
        ws = _make_mock_ws([])
        importer = _make_importer(ws)
        rows = [
            {'sku': f'PORT-{i:03d}', 'title_ko': f'상품{i}', 'buy_currency': 'JPY',
             'buy_price': '10000', 'vendor': 'porter', 'status': 'active',
             'title_en': '', 'title_ja': '', 'title_fr': '',
             'src_url': f'http://example.com/{i}', 'source_country': 'JP',
             'images': '', 'stock': 0, 'tags': ''}
            for i in range(3)
        ]
        result = importer.upsert_rows(rows)
        assert result['added'] == 3


class TestSheetImporterUpsertExisting:
    """test_sheet_importer_upsert_existing: 기존 행 업데이트 테스트 (mock)"""

    def test_existing_rows_are_updated(self):
        existing = [
            {'sku': 'PORT-001', 'buy_price': '10000', 'buy_currency': 'JPY',
             'stock': 0, 'images': ''}
        ]
        ws = _make_mock_ws(existing)
        importer = _make_importer(ws)
        rows = [
            {'sku': 'PORT-001', 'title_ko': '상품A', 'buy_currency': 'JPY',
             'buy_price': '12000', 'vendor': 'porter', 'status': 'active',
             'title_en': '', 'title_ja': '', 'title_fr': '',
             'src_url': 'http://example.com/1', 'source_country': 'JP',
             'images': '', 'stock': 5, 'tags': ''},
        ]
        result = importer.upsert_rows(rows)
        assert result['updated'] == 1
        assert result['added'] == 0

    def test_update_cell_called_for_price(self):
        existing = [
            {'sku': 'MEMO-001', 'buy_price': '200', 'buy_currency': 'EUR',
             'stock': 0, 'images': ''}
        ]
        ws = _make_mock_ws(existing)
        importer = _make_importer(ws)
        rows = [
            {'sku': 'MEMO-001', 'title_ko': '', 'buy_currency': 'EUR',
             'buy_price': '280', 'vendor': 'memo_paris', 'status': 'active',
             'title_en': 'Product', 'title_ja': '', 'title_fr': 'Produit',
             'src_url': 'http://memo.com/1', 'source_country': 'FR',
             'images': '', 'stock': 10, 'tags': ''},
        ]
        importer.upsert_rows(rows)
        # update_cell이 최소 1번은 호출되어야 함
        assert ws.update_cell.call_count >= 1


class TestSheetImporterSkipDuplicate:
    """test_sheet_importer_skip_duplicate: 중복 SKU 스킵 테스트 (mock)"""

    def test_duplicate_skus_not_appended(self):
        existing = [{'sku': 'PORT-DUP', 'title_ko': '기존상품'}]
        ws = _make_mock_ws(existing)
        importer = _make_importer(ws)
        rows = [
            {'sku': 'PORT-DUP', 'title_ko': '중복상품', 'buy_currency': 'JPY',
             'buy_price': '10000', 'vendor': 'porter', 'status': 'active',
             'title_en': '', 'title_ja': '', 'title_fr': '',
             'src_url': 'http://example.com/dup', 'source_country': 'JP',
             'images': '', 'stock': 0, 'tags': ''},
        ]
        result = importer.upsert_rows(rows)
        assert result['added'] == 0
        ws.append_rows.assert_not_called()

    def test_mixed_new_and_existing(self):
        existing = [{'sku': 'PORT-EXIST'}]
        ws = _make_mock_ws(existing)
        importer = _make_importer(ws)
        rows = [
            {'sku': 'PORT-EXIST', 'buy_currency': 'JPY', 'buy_price': '10000',
             'title_ko': '', 'title_en': '', 'title_ja': '', 'title_fr': '',
             'src_url': '', 'source_country': 'JP', 'images': '', 'stock': 0,
             'tags': '', 'vendor': 'porter', 'status': 'active'},
            {'sku': 'PORT-NEW', 'buy_currency': 'JPY', 'buy_price': '20000',
             'title_ko': '', 'title_en': '', 'title_ja': '', 'title_fr': '',
             'src_url': '', 'source_country': 'JP', 'images': '', 'stock': 0,
             'tags': '', 'vendor': 'porter', 'status': 'active'},
        ]
        result = importer.upsert_rows(rows)
        assert result['added'] == 1
        assert result['updated'] == 1


# ──────────────────────────────────────────────────────────────────────────────
# import_from_file E2E 테스트 (mock)
# ──────────────────────────────────────────────────────────────────────────────

class TestImportFromFilePorter:
    """test_import_from_file_porter: 포터 파일 → 시트 적재 E2E (mock)"""

    def test_porter_sample_import(self):
        ws = _make_mock_ws([])
        with patch('src.scrapers.sheet_importer.open_sheet', return_value=ws):
            from src.scrapers.sheet_importer import SheetImporter
            importer = SheetImporter(sheet_id='test-id')
            result = importer.import_from_file(PORTER_SAMPLE, 'porter')
        assert result['added'] == 5
        assert result['updated'] == 0
        assert len(result['errors']) == 0

    def test_porter_skus_are_generated(self):
        ws = _make_mock_ws([])
        captured_rows = []

        def capture_append(values, **kwargs):
            captured_rows.extend(values)

        ws.append_rows.side_effect = capture_append
        with patch('src.scrapers.sheet_importer.open_sheet', return_value=ws):
            from src.scrapers.sheet_importer import SheetImporter
            importer = SheetImporter(sheet_id='test-id')
            importer.import_from_file(PORTER_SAMPLE, 'porter')
        # 각 행의 SKU(첫 번째 컬럼)가 'PORT-' 접두어를 가져야 함
        for row in captured_rows:
            assert row[0].startswith('PORT-')


class TestImportFromFileMemo:
    """test_import_from_file_memo: 메모파리 파일 → 시트 적재 E2E (mock)"""

    def test_memo_sample_import(self):
        ws = _make_mock_ws([])
        with patch('src.scrapers.sheet_importer.open_sheet', return_value=ws):
            from src.scrapers.sheet_importer import SheetImporter
            importer = SheetImporter(sheet_id='test-id')
            result = importer.import_from_file(MEMO_SAMPLE, 'memo_paris')
        assert result['added'] == 4
        assert result['updated'] == 0
        assert len(result['errors']) == 0

    def test_memo_vendor_field(self):
        ws = _make_mock_ws([])
        captured_rows = []

        def capture_append(values, **kwargs):
            captured_rows.extend(values)

        ws.append_rows.side_effect = capture_append
        with patch('src.scrapers.sheet_importer.open_sheet', return_value=ws):
            from src.scrapers.sheet_importer import SheetImporter
            importer = SheetImporter(sheet_id='test-id')
            importer.import_from_file(MEMO_SAMPLE, 'memo_paris')
        # vendor 컬럼(인덱스 12)이 'memo_paris'여야 함
        from src.scrapers.sheet_importer import CATALOG_HEADERS
        vendor_idx = CATALOG_HEADERS.index('vendor')
        for row in captured_rows:
            assert row[vendor_idx] == 'memo_paris'

    def test_invalid_file_returns_error(self):
        ws = _make_mock_ws([])
        with patch('src.scrapers.sheet_importer.open_sheet', return_value=ws):
            from src.scrapers.sheet_importer import SheetImporter
            importer = SheetImporter(sheet_id='test-id')
            result = importer.import_from_file('/nonexistent/file.csv', 'memo_paris')
        assert result['added'] == 0
        assert len(result['errors']) > 0


# ──────────────────────────────────────────────────────────────────────────────
# CLI dry-run 테스트
# ──────────────────────────────────────────────────────────────────────────────

class TestCliDryRun:
    """test_cli_dry_run: CLI dry-run 모드 테스트"""

    def test_dry_run_porter_exits_zero(self, capsys):
        from src.scrapers.cli import main
        # dry-run은 Google Sheets 연결 없이 실행 가능
        with pytest.raises(SystemExit) as exc_info:
            main(['--vendor', 'porter', '--file', PORTER_SAMPLE, '--dry-run'])
        assert exc_info.value.code == 0

    def test_dry_run_memo_exits_zero(self, capsys):
        from src.scrapers.cli import main
        with pytest.raises(SystemExit) as exc_info:
            main(['--vendor', 'memo_paris', '--file', MEMO_SAMPLE, '--dry-run'])
        assert exc_info.value.code == 0

    def test_dry_run_output_contains_vendor(self, capsys):
        from src.scrapers.cli import main
        with pytest.raises(SystemExit):
            main(['--vendor', 'porter', '--file', PORTER_SAMPLE, '--dry-run'])
        captured = capsys.readouterr()
        assert 'porter' in captured.out

    def test_dry_run_no_sheet_id_required(self, capsys):
        """dry-run 모드는 GOOGLE_SHEET_ID 없이도 실행되어야 함."""
        from src.scrapers.cli import main
        env_patch = {'GOOGLE_SHEET_ID': ''}
        with patch.dict(os.environ, env_patch):
            with pytest.raises(SystemExit) as exc_info:
                main(['--vendor', 'porter', '--file', PORTER_SAMPLE, '--dry-run'])
        assert exc_info.value.code == 0

    def test_missing_sheet_id_exits_nonzero(self):
        """dry-run 아닌 경우 sheet-id 없으면 오류 종료."""
        from src.scrapers.cli import main
        with patch.dict(os.environ, {'GOOGLE_SHEET_ID': ''}):
            with pytest.raises(SystemExit) as exc_info:
                main(['--vendor', 'porter', '--file', PORTER_SAMPLE])
        assert exc_info.value.code != 0

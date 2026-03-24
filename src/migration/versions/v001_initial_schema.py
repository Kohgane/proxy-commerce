"""
v001_initial_schema — 초기 스키마 정의.

catalog, orders, fx_history, fx_rates, audit_log, daily_exports 워크시트의
헤더(컬럼 목록)를 정의하고 필요 시 생성한다.
"""

VERSION = "001"
DESCRIPTION = "초기 스키마 — 기본 워크시트 헤더 정의"

# 워크시트별 헤더 컬럼 정의
WORKSHEET_SCHEMAS = {
    "catalog": [
        "sku", "title_ko", "title_en", "title_ja", "title_fr",
        "src_url", "buy_currency", "buy_price", "source_country",
        "images", "stock", "tags", "vendor", "status",
        "category", "brand", "forwarder", "customs_category",
        "created_at", "updated_at",
    ],
    "orders": [
        "order_id", "channel", "status", "customer_name", "customer_email",
        "items_json", "total_krw", "total_foreign", "currency",
        "shipping_method", "tracking_number", "vendor",
        "created_at", "updated_at", "notes",
    ],
    "fx_history": [
        "date", "pair", "rate", "source", "change_pct", "recorded_at",
    ],
    "fx_rates": [
        "pair", "rate", "source", "updated_at",
    ],
    "audit_log": [
        "event_id", "event_type", "entity_type", "entity_id",
        "old_value", "new_value", "user", "timestamp", "notes",
    ],
    "daily_exports": [
        "export_date", "export_type", "row_count", "file_name",
        "status", "created_at", "notes",
    ],
}


def up(client, sheet_id: str) -> None:
    """초기 스키마를 적용한다.

    각 워크시트가 없으면 생성하고 헤더 행을 입력한다.
    이미 존재하는 워크시트는 수정하지 않는다.

    인자:
        client: gspread 클라이언트
        sheet_id: 스프레드시트 ID
    """
    if client is None:
        raise ValueError("gspread 클라이언트가 필요합니다.")

    spreadsheet = client.open_by_key(sheet_id)
    existing = {ws.title for ws in spreadsheet.worksheets()}

    for ws_name, headers in WORKSHEET_SCHEMAS.items():
        if ws_name in existing:
            continue
        ws = spreadsheet.add_worksheet(ws_name, rows=1000, cols=len(headers))
        ws.update("A1", [headers])

    import logging
    logging.getLogger(__name__).info("v001 up: 초기 스키마 적용 완료")


def down(client, sheet_id: str) -> None:
    """초기 스키마 롤백 — v001에서 생성한 워크시트를 삭제한다.

    주의: 데이터가 있는 워크시트도 삭제되므로 주의해서 사용.

    인자:
        client: gspread 클라이언트
        sheet_id: 스프레드시트 ID
    """
    if client is None:
        raise ValueError("gspread 클라이언트가 필요합니다.")

    spreadsheet = client.open_by_key(sheet_id)
    ws_map = {ws.title: ws for ws in spreadsheet.worksheets()}

    for ws_name in WORKSHEET_SCHEMAS:
        if ws_name in ws_map:
            spreadsheet.del_worksheet(ws_map[ws_name])

    import logging
    logging.getLogger(__name__).info("v001 down: 초기 스키마 롤백 완료")

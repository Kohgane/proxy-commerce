"""src/cli/inventory_commands.py — 재고 관련 CLI 커맨드.

커맨드:
  inventory check [--vendor porter|memo_paris]   — 재고 확인
  inventory low-stock [--threshold N]            — 재고 부족 상품
  inventory sync [--vendor porter|memo_paris]    — 재고 동기화
"""

import logging
import os

try:
    from ..utils.sheets import open_sheet
except ImportError:
    open_sheet = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


def _load_catalog():
    """Google Sheets에서 카탈로그를 로드한다."""
    try:
        sheet_id = os.getenv("GOOGLE_SHEET_ID", "")
        ws = open_sheet(sheet_id, os.getenv("WORKSHEET", "catalog"))
        return ws.get_all_records()
    except Exception as exc:
        logger.warning("카탈로그 로드 실패: %s", exc)
        return []


def cmd_inventory(args):
    """재고 관련 커맨드를 처리한다."""
    sub = getattr(args, "inv_cmd", None)
    if sub == "low-stock":
        _inventory_low_stock(args)
    elif sub == "sync":
        _inventory_sync(args)
    else:
        _inventory_check(args)


def _inventory_check(args):
    """재고 현황을 출력한다."""
    vendor_filter = getattr(args, "vendor", None)
    catalog = _load_catalog()

    if vendor_filter:
        catalog = [c for c in catalog if str(c.get("vendor", "")).lower() == vendor_filter.lower()]

    if not catalog:
        print("조회된 재고 없음")
        return

    print(f"\n📦 재고 현황 ({len(catalog)}개 상품)")
    print("─" * 72)
    print(f"{'SKU':<20} {'벤더':<12} {'재고':<8} {'상태':<12} {'가격(KRW)'}")
    print("─" * 72)
    for c in catalog:
        print(
            f"{str(c.get('sku', '')):<20} "
            f"{str(c.get('vendor', '')):<12} "
            f"{str(c.get('stock', '')):<8} "
            f"{str(c.get('stock_status', '')):<12} "
            f"{str(c.get('sell_price_krw', ''))}"
        )


def _inventory_low_stock(args):
    """재고 부족 상품을 출력한다."""
    threshold = getattr(args, "threshold", 3)
    catalog = _load_catalog()
    low_stock = [c for c in catalog if int(c.get("stock", 0) or 0) <= threshold]

    if not low_stock:
        print(f"✅ 재고 부족 상품 없음 (기준: {threshold}개 이하)")
        return

    print(f"\n⚠️  재고 부족 상품 (기준: {threshold}개 이하) — {len(low_stock)}개")
    print("─" * 60)
    for c in low_stock:
        sku = c.get("sku", "")
        stock = c.get("stock", 0)
        vendor = c.get("vendor", "")
        print(f"  • {sku} [{vendor}] 재고: {stock}개")


def _inventory_sync(args):
    """재고 동기화를 실행한다."""
    vendor_filter = getattr(args, "vendor", None)
    print(f"🔄 재고 동기화 시작... (vendor={vendor_filter or 'all'})")
    try:
        from ..inventory.inventory_sync import InventorySync
        syncer = InventorySync()
        syncer.full_sync(vendor_filter=vendor_filter)
        print("✅ 재고 동기화 완료")
    except Exception as exc:
        print(f"❌ 재고 동기화 실패: {exc}")

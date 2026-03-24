"""src/cli/order_commands.py — 주문/환율 관련 CLI 커맨드.

커맨드:
  sync                           — 카탈로그 동기화
  orders list [--status] [--limit]  — 주문 목록
  orders detail <order_id>          — 주문 상세
  orders stats [--period]           — 주문 통계
  fx show                            — 현재 환율 출력
  fx update                          — 환율 업데이트
"""

import datetime
import logging
import os

try:
    from ..utils.sheets import open_sheet
except ImportError:
    open_sheet = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


def _load_orders():
    """Google Sheets에서 주문 목록을 로드한다."""
    try:
        sheet_id = os.getenv("GOOGLE_SHEET_ID", "")
        ws = open_sheet(sheet_id, os.getenv("ORDERS_WORKSHEET", "orders"))
        return ws.get_all_records()
    except Exception as exc:
        logger.warning("주문 로드 실패: %s", exc)
        return []


def cmd_sync(args):
    """카탈로그 동기화를 실행한다."""
    print("🔄 카탈로그 동기화 시작...")
    try:
        from ..catalog_sync import main as sync_main
        sync_main()
        print("✅ 카탈로그 동기화 완료")
    except Exception as exc:
        print(f"❌ 동기화 실패: {exc}")


def cmd_orders(args):
    """주문 관련 커맨드를 처리한다."""
    sub = getattr(args, "orders_cmd", None)
    if sub == "list" or sub is None:
        _orders_list(args)
    elif sub == "detail":
        _orders_detail(args)
    elif sub == "stats":
        _orders_stats(args)


def _orders_list(args):
    """주문 목록을 출력한다."""
    orders = _load_orders()
    status_filter = getattr(args, "status", None)
    limit = getattr(args, "limit", 20)

    if status_filter:
        orders = [o for o in orders if str(o.get("status", "")).lower() == status_filter.lower()]

    orders = orders[:limit]
    if not orders:
        print("조회된 주문 없음")
        return

    print(f"{'주문번호':<12} {'고객명':<12} {'상태':<10} {'금액(KRW)':<12} {'날짜':<22}")
    print("─" * 72)
    for o in orders:
        print(
            f"{str(o.get('order_number', '')):<12} "
            f"{str(o.get('customer_name', '')):<12} "
            f"{str(o.get('status', '')):<10} "
            f"{str(o.get('sell_price_krw', '')):<12} "
            f"{str(o.get('order_date', '')):<22}"
        )


def _orders_detail(args):
    """주문 상세 정보를 출력한다."""
    order_id = args.order_id
    orders = _load_orders()
    for o in orders:
        if str(o.get("order_id", "")) == order_id or str(o.get("order_number", "")) == order_id:
            print(f"\n📦 주문 상세: {order_id}")
            print("─" * 40)
            for k, v in o.items():
                print(f"  {k}: {v}")
            return
    print(f"주문을 찾을 수 없습니다: {order_id}")


def _orders_stats(args):
    """주문 통계를 출력한다."""
    period = getattr(args, "period", "today")
    orders = _load_orders()
    now = datetime.datetime.now(tz=datetime.timezone.utc)

    if period == "today":
        cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        cutoff = now - datetime.timedelta(weeks=1)
    else:
        cutoff = now - datetime.timedelta(days=30)

    filtered = []
    for o in orders:
        val = str(o.get("order_date", ""))
        try:
            dt = datetime.datetime.fromisoformat(val.replace("Z", "+00:00"))
            if dt >= cutoff:
                filtered.append(o)
        except (ValueError, TypeError):
            continue

    total_revenue = sum(float(o.get("sell_price_krw", 0) or 0) for o in filtered)
    print(f"\n📊 주문 통계 ({period})")
    print("─" * 40)
    print(f"  총 주문 수: {len(filtered)}건")
    print(f"  총 매출: {total_revenue:,.0f}원")


def cmd_fx(args):
    """환율 관련 커맨드를 처리한다."""
    sub = getattr(args, "fx_cmd", "show")
    if sub == "update":
        _fx_update()
    else:
        _fx_show()


def _fx_show():
    """현재 환율을 출력한다."""
    try:
        from ..fx.provider import FXProvider
        rates = FXProvider().get_rates()
        print("\n💱 현재 환율")
        print("─" * 30)
        for pair, rate in rates.items():
            if not callable(rate):
                print(f"  {pair}: {float(rate):,.2f}")
    except Exception as exc:
        print(f"❌ 환율 조회 실패: {exc}")


def _fx_update():
    """환율을 업데이트한다."""
    print("🔄 환율 업데이트 중...")
    try:
        from ..fx.provider import FXProvider
        FXProvider().get_rates()
        print("✅ 환율 업데이트 완료")
    except Exception as exc:
        print(f"❌ 환율 업데이트 실패: {exc}")

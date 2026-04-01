"""주문 알림 CLI 엔트리포인트.

Usage::

    # 쿠팡 주문 폴링 시작 (포그라운드)
    python -m src.order_alerts.cli poll --platform coupang

    # 네이버 주문 폴링 시작
    python -m src.order_alerts.cli poll --platform naver

    # 양 플랫폼 동시 폴링
    python -m src.order_alerts.cli poll --platform all

    # 특정 주문 상태 조회
    python -m src.order_alerts.cli status --order-id ORD-001

    # 최근 알림 이력 조회
    python -m src.order_alerts.cli history --limit 20
"""

import argparse
import logging
import os
import threading

logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
logger = logging.getLogger(__name__)


def _cmd_poll(args):
    """주문 폴링 실행."""
    from .alert_dispatcher import AlertDispatcher
    from .order_tracker import OrderTracker
    from .coupang_order_poller import CoupangOrderPoller
    from .naver_order_poller import NaverOrderPoller

    dispatcher = AlertDispatcher()
    tracker = OrderTracker()

    def handle_orders(orders):
        new_orders = tracker.filter_new_orders(orders)
        if not new_orders:
            logger.info("신규 주문 없음")
            return
        logger.info("신규 주문 %d건 처리 중", len(new_orders))
        for order in new_orders:
            sent = dispatcher.send_new_order_alert(order)
            if sent:
                tracker.mark_alerted(order)
                logger.info("알림 발송: %s [%s]", order.get('order_number'), order.get('platform'))

    platform = args.platform.lower()
    threads = []

    if platform in ('coupang', 'all'):
        poller = CoupangOrderPoller(poll_interval=args.interval)
        t = threading.Thread(
            target=poller.poll_loop,
            kwargs={'callback': handle_orders},
            daemon=True,
            name='coupang-poller',
        )
        threads.append(t)

    if platform in ('naver', 'all'):
        poller = NaverOrderPoller(poll_interval=args.interval)
        t = threading.Thread(
            target=poller.poll_loop,
            kwargs={'callback': handle_orders},
            daemon=True,
            name='naver-poller',
        )
        threads.append(t)

    if not threads:
        print(f"알 수 없는 플랫폼: {args.platform}")
        return

    for t in threads:
        t.start()
        logger.info("폴링 스레드 시작: %s", t.name)

    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        logger.info("폴링 중단됨")


def _cmd_status(args):
    """주문 상태 조회."""
    from .order_tracker import OrderTracker
    tracker = OrderTracker()
    history = tracker.get_order_history(args.order_id)
    if not history:
        print(f"주문 이력 없음: {args.order_id}")
        return
    print(f"\n주문 이력: {args.order_id}")
    print("-" * 60)
    for row in history:
        print(f"  {row.get('alerted_at', '')[:19]}  [{row.get('platform', '')}]  {row.get('status', '')}")


def _cmd_history(args):
    """최근 알림 이력 조회."""
    from .order_tracker import OrderTracker
    tracker = OrderTracker()
    records = tracker.get_alerted_orders(limit=args.limit)
    if not records:
        print("알림 이력이 없습니다.")
        return
    print(f"\n최근 알림 이력 (최대 {args.limit}건)")
    print("-" * 80)
    for row in records:
        print(
            f"  {row.get('alerted_at', '')[:19]}  "
            f"[{row.get('platform', '')}]  "
            f"{row.get('order_number', '')}  "
            f"{row.get('status', '')}  "
            f"{row.get('product_names', '')[:30]}"
        )


def main():
    """CLI 메인 엔트리포인트."""
    parser = argparse.ArgumentParser(
        prog='order_alerts',
        description='주문 접수 텔레그램 알림 시스템',
    )
    subparsers = parser.add_subparsers(dest='command', required=True)

    # poll 서브커맨드
    poll_parser = subparsers.add_parser('poll', help='주문 폴링 시작')
    poll_parser.add_argument(
        '--platform',
        choices=['coupang', 'naver', 'all'],
        default='all',
        help='폴링할 플랫폼 (기본: all)',
    )
    poll_parser.add_argument(
        '--interval',
        type=int,
        default=int(os.getenv('ORDER_POLL_INTERVAL_SECONDS', '300')),
        help='폴링 간격(초, 기본 300)',
    )

    # status 서브커맨드
    status_parser = subparsers.add_parser('status', help='주문 상태 조회')
    status_parser.add_argument('--order-id', required=True, help='주문 ID')

    # history 서브커맨드
    history_parser = subparsers.add_parser('history', help='알림 이력 조회')
    history_parser.add_argument('--limit', type=int, default=20, help='최대 조회 건수 (기본 20)')

    args = parser.parse_args()

    if args.command == 'poll':
        _cmd_poll(args)
    elif args.command == 'status':
        _cmd_status(args)
    elif args.command == 'history':
        _cmd_history(args)


if __name__ == '__main__':
    main()

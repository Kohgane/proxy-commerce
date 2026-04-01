"""tests/test_cli_commands.py — CLI 커맨드 테스트."""

from unittest.mock import MagicMock, patch

from src.cli.main import _build_parser


class TestCliParser:
    def test_parser_sync(self):
        """sync 커맨드 파싱 테스트."""
        parser = _build_parser()
        args = parser.parse_args(["sync"])
        assert args.command == "sync"

    def test_parser_orders_list(self):
        """orders list 커맨드 파싱 테스트."""
        parser = _build_parser()
        args = parser.parse_args(["orders", "list", "--status", "shipped", "--limit", "10"])
        assert args.command == "orders"
        assert args.orders_cmd == "list"
        assert args.status == "shipped"
        assert args.limit == 10

    def test_parser_inventory_low_stock(self):
        """inventory low-stock 커맨드 파싱 테스트."""
        parser = _build_parser()
        args = parser.parse_args(["inventory", "low-stock", "--threshold", "5"])
        assert args.command == "inventory"
        assert args.inv_cmd == "low-stock"
        assert args.threshold == 5

    def test_parser_export_orders(self):
        """export orders 커맨드 파싱 테스트."""
        parser = _build_parser()
        args = parser.parse_args(["export", "orders", "--from", "2026-01-01", "--to", "2026-01-31"])
        assert args.command == "export"
        assert args.exp_cmd == "orders"
        assert args.date_from == "2026-01-01"
        assert args.date_to == "2026-01-31"

    def test_parser_health_check(self):
        """health check 커맨드 파싱 테스트."""
        parser = _build_parser()
        args = parser.parse_args(["health", "check"])
        assert args.command == "health"

    def test_parser_cache_stats(self):
        """cache stats 커맨드 파싱 테스트."""
        parser = _build_parser()
        args = parser.parse_args(["cache", "stats"])
        assert args.command == "cache"
        assert args.cache_cmd == "stats"

    def test_parser_audit_recent(self):
        """audit recent 커맨드 파싱 테스트."""
        parser = _build_parser()
        args = parser.parse_args(["audit", "recent", "--limit", "5"])
        assert args.limit == 5


class TestOrderCommands:
    def test_orders_list_output(self, capsys, sample_order_rows):
        """orders list 출력 테스트."""
        with patch("src.cli.order_commands.open_sheet") as mock_open:
            ws = MagicMock()
            ws.get_all_records.return_value = sample_order_rows
            mock_open.return_value = ws
            parser = _build_parser()
            args = parser.parse_args(["orders", "list"])
            from src.cli.order_commands import cmd_orders
            cmd_orders(args)

        captured = capsys.readouterr()
        assert "주문번호" in captured.out

    def test_orders_detail_found(self, capsys, sample_order_rows):
        """orders detail 출력 테스트 — 주문 존재."""
        with patch("src.cli.order_commands.open_sheet") as mock_open:
            ws = MagicMock()
            ws.get_all_records.return_value = sample_order_rows
            mock_open.return_value = ws
            parser = _build_parser()
            args = parser.parse_args(["orders", "detail", "10001"])
            from src.cli.order_commands import cmd_orders
            cmd_orders(args)

        captured = capsys.readouterr()
        assert "10001" in captured.out

    def test_orders_detail_not_found(self, capsys, sample_order_rows):
        """orders detail 출력 테스트 — 주문 없음."""
        with patch("src.cli.order_commands.open_sheet") as mock_open:
            ws = MagicMock()
            ws.get_all_records.return_value = sample_order_rows
            mock_open.return_value = ws
            parser = _build_parser()
            args = parser.parse_args(["orders", "detail", "99999"])
            from src.cli.order_commands import cmd_orders
            cmd_orders(args)

        captured = capsys.readouterr()
        assert "찾을 수 없습니다" in captured.out


class TestInventoryCommands:
    def test_inventory_check_output(self, capsys, sample_catalog_rows):
        """inventory check 출력 테스트."""
        with patch("src.cli.inventory_commands.open_sheet") as mock_open:
            ws = MagicMock()
            ws.get_all_records.return_value = sample_catalog_rows
            mock_open.return_value = ws
            parser = _build_parser()
            args = parser.parse_args(["inventory", "check"])
            from src.cli.inventory_commands import cmd_inventory
            cmd_inventory(args)

        captured = capsys.readouterr()
        assert "재고 현황" in captured.out

    def test_inventory_low_stock_output(self, capsys, sample_catalog_rows):
        """inventory low-stock 출력 테스트."""
        with patch("src.cli.inventory_commands.open_sheet") as mock_open:
            ws = MagicMock()
            ws.get_all_records.return_value = sample_catalog_rows
            mock_open.return_value = ws
            parser = _build_parser()
            args = parser.parse_args(["inventory", "low-stock", "--threshold", "10"])
            from src.cli.inventory_commands import cmd_inventory
            cmd_inventory(args)

        captured = capsys.readouterr()
        # 모든 항목이 임계값 이하이므로 출력됨
        assert captured.out  # 비어있지 않음


class TestSystemCommands:
    def test_cache_stats_output(self, capsys):
        """cache stats 출력 테스트."""
        parser = _build_parser()
        args = parser.parse_args(["cache", "stats"])
        from src.cli.system_commands import cmd_cache
        cmd_cache(args)

        captured = capsys.readouterr()
        assert "캐시 통계" in captured.out

    def test_cache_clear_output(self, capsys):
        """cache clear 출력 테스트."""
        parser = _build_parser()
        args = parser.parse_args(["cache", "clear"])
        from src.cli.system_commands import cmd_cache
        cmd_cache(args)

        captured = capsys.readouterr()
        assert "완료" in captured.out

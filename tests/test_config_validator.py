"""tests/test_config_validator.py — ConfigValidator 단위 테스트."""


class TestConfigValidatorRequired:
    """필수 필드 검증 테스트."""

    def test_validate_missing_required(self, monkeypatch):
        """필수 환경변수가 누락된 경우 오류가 반환된다."""
        # GOOGLE_SERVICE_JSON_B64 와 GOOGLE_SHEET_ID 는 required=True
        monkeypatch.delenv('GOOGLE_SERVICE_JSON_B64', raising=False)
        monkeypatch.delenv('GOOGLE_SHEET_ID', raising=False)

        from src.config.validator import ConfigValidator
        validator = ConfigValidator()
        is_valid, warnings, errors = validator.validate()

        assert is_valid is False
        assert any('GOOGLE_SERVICE_JSON_B64' in e or 'GOOGLE_SHEET_ID' in e for e in errors)

    def test_validate_ok_with_required_fields(self, monkeypatch):
        """필수 환경변수가 모두 설정된 경우 오류가 없다."""
        monkeypatch.setenv('GOOGLE_SERVICE_JSON_B64', 'dGVzdA==')
        monkeypatch.setenv('GOOGLE_SHEET_ID', 'sheet_id_test')

        from src.config.validator import ConfigValidator
        validator = ConfigValidator()
        is_valid, warnings, errors = validator.validate()

        # 필수 필드 오류가 없어야 함
        required_errors = [e for e in errors if 'GOOGLE_SERVICE_JSON_B64' in e or 'GOOGLE_SHEET_ID' in e]
        assert len(required_errors) == 0


class TestConfigValidatorTypeChecks:
    """타입 검증 테스트."""

    def test_validate_type_int_invalid(self, monkeypatch):
        """PORT에 숫자가 아닌 값이 설정된 경우 타입 오류가 반환된다."""
        monkeypatch.setenv('PORT', 'abc_not_a_number')

        from src.config.validator import ConfigValidator
        validator = ConfigValidator()
        ok, msg = validator.validate_field('PORT', 'abc_not_a_number')

        assert ok is False
        assert 'PORT' in msg

    def test_validate_type_int_valid(self, monkeypatch):
        """PORT에 유효한 숫자가 설정된 경우 오류가 없다."""
        from src.config.validator import ConfigValidator
        validator = ConfigValidator()
        ok, msg = validator.validate_field('PORT', '8080')

        assert ok is True


class TestConfigValidatorRangeChecks:
    """범위 검증 테스트."""

    def test_validate_port_range_too_high(self):
        """PORT > 65535 시 범위 오류가 반환된다."""
        from src.config.validator import ConfigValidator
        validator = ConfigValidator()
        ok, msg = validator.validate_field('PORT', '99999')

        assert ok is False
        assert '범위' in msg or 'PORT' in msg

    def test_validate_port_range_too_low(self):
        """PORT = 0 시 범위 오류가 반환된다."""
        from src.config.validator import ConfigValidator
        validator = ConfigValidator()
        ok, msg = validator.validate_field('PORT', '0')

        assert ok is False

    def test_validate_port_range_valid(self):
        """PORT = 8000 시 오류가 없다."""
        from src.config.validator import ConfigValidator
        validator = ConfigValidator()
        ok, msg = validator.validate_field('PORT', '8000')

        assert ok is True

    def test_validate_margin_range(self):
        """TARGET_MARGIN_PCT > 100 시 범위 오류."""
        from src.config.validator import ConfigValidator
        validator = ConfigValidator()
        ok, msg = validator.validate_field('TARGET_MARGIN_PCT', '150')

        assert ok is False


class TestConfigValidatorDependency:
    """의존성 검증 테스트."""

    def test_validate_dependency_shopify_shop_without_token(self, monkeypatch):
        """SHOPIFY_SHOP 설정 시 SHOPIFY_ACCESS_TOKEN 미설정이면 경고."""
        monkeypatch.setenv('GOOGLE_SERVICE_JSON_B64', 'dGVzdA==')
        monkeypatch.setenv('GOOGLE_SHEET_ID', 'test_id')
        monkeypatch.setenv('SHOPIFY_SHOP', 'mystore.myshopify.com')
        monkeypatch.delenv('SHOPIFY_ACCESS_TOKEN', raising=False)

        from src.config.validator import ConfigValidator
        validator = ConfigValidator()
        is_valid, warnings, errors = validator.validate()

        assert any('SHOPIFY_ACCESS_TOKEN' in w for w in warnings)

    def test_validate_dependency_satisfied(self, monkeypatch):
        """SHOPIFY_SHOP + SHOPIFY_ACCESS_TOKEN 모두 설정 시 경고 없음."""
        monkeypatch.setenv('GOOGLE_SERVICE_JSON_B64', 'dGVzdA==')
        monkeypatch.setenv('GOOGLE_SHEET_ID', 'test_id')
        monkeypatch.setenv('SHOPIFY_SHOP', 'mystore.myshopify.com')
        monkeypatch.setenv('SHOPIFY_ACCESS_TOKEN', 'shpat_test')
        monkeypatch.setenv('SHOPIFY_CLIENT_SECRET', 'secret')

        from src.config.validator import ConfigValidator
        validator = ConfigValidator()
        is_valid, warnings, errors = validator.validate()

        shopify_warnings = [w for w in warnings if 'SHOPIFY_ACCESS_TOKEN' in w]
        assert len(shopify_warnings) == 0

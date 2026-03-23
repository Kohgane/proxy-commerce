"""Tests for scripts/validate_env.py."""

from scripts.validate_env import validate_secrets, is_placeholder


class TestIsPlaceholder:
    def test_detects_placeholder(self):
        assert is_placeholder('${STAGING_FOO}') is True

    def test_real_value_not_placeholder(self):
        assert is_placeholder('shpat_abc123') is False

    def test_empty_string_not_placeholder(self):
        assert is_placeholder('') is False


class TestStagingValidation:
    def test_success_with_all_required_secrets(self, monkeypatch):
        monkeypatch.setenv('GOOGLE_SERVICE_JSON_B64', 'dGVzdA==')
        monkeypatch.setenv('GOOGLE_SHEET_ID', '1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms')
        monkeypatch.setenv('SHOPIFY_SHOP', 'test-store.myshopify.com')
        monkeypatch.setenv('SHOPIFY_ACCESS_TOKEN', 'shpat_abc123def456')
        monkeypatch.setenv('SHOPIFY_CLIENT_SECRET', 'shpss_xyz789')

        result = validate_secrets('staging')

        assert result['passed'] is True
        assert result['errors'] == []

    def test_failure_when_secret_missing(self, monkeypatch):
        monkeypatch.delenv('GOOGLE_SERVICE_JSON_B64', raising=False)
        monkeypatch.delenv('GOOGLE_SHEET_ID', raising=False)
        monkeypatch.delenv('SHOPIFY_SHOP', raising=False)
        monkeypatch.delenv('SHOPIFY_ACCESS_TOKEN', raising=False)
        monkeypatch.delenv('SHOPIFY_CLIENT_SECRET', raising=False)

        result = validate_secrets('staging')

        assert result['passed'] is False
        assert len(result['errors']) > 0

    def test_failure_when_placeholder_not_replaced(self, monkeypatch):
        monkeypatch.setenv('GOOGLE_SERVICE_JSON_B64', '${STAGING_GOOGLE_SERVICE_JSON_B64}')
        monkeypatch.setenv('GOOGLE_SHEET_ID', '${STAGING_GOOGLE_SHEET_ID}')
        monkeypatch.setenv('SHOPIFY_SHOP', '${STAGING_SHOPIFY_SHOP}')
        monkeypatch.setenv('SHOPIFY_ACCESS_TOKEN', '${STAGING_SHOPIFY_ACCESS_TOKEN}')
        monkeypatch.setenv('SHOPIFY_CLIENT_SECRET', '${STAGING_SHOPIFY_CLIENT_SECRET}')

        result = validate_secrets('staging')

        assert result['passed'] is False
        assert any('placeholder' in e for e in result['errors'])


class TestProductionValidation:
    def test_failure_when_woo_secrets_missing(self, monkeypatch):
        monkeypatch.setenv('GOOGLE_SERVICE_JSON_B64', 'dGVzdA==')
        monkeypatch.setenv('GOOGLE_SHEET_ID', 'sheet_id')
        monkeypatch.setenv('SHOPIFY_SHOP', 'shop.myshopify.com')
        monkeypatch.setenv('SHOPIFY_ACCESS_TOKEN', 'shpat_abc')
        monkeypatch.setenv('SHOPIFY_CLIENT_SECRET', 'shpss_xyz')
        monkeypatch.delenv('WOO_BASE_URL', raising=False)
        monkeypatch.delenv('WOO_CK', raising=False)
        monkeypatch.delenv('WOO_CS', raising=False)

        result = validate_secrets('production')

        assert result['passed'] is False
        woo_errors = [e for e in result['errors'] if 'WOO' in e]
        assert len(woo_errors) > 0

    def test_optional_secrets_produce_warnings(self, monkeypatch):
        monkeypatch.setenv('GOOGLE_SERVICE_JSON_B64', 'dGVzdA==')
        monkeypatch.setenv('GOOGLE_SHEET_ID', 'sheet_id')
        monkeypatch.setenv('SHOPIFY_SHOP', 'shop.myshopify.com')
        monkeypatch.setenv('SHOPIFY_ACCESS_TOKEN', 'shpat_abc')
        monkeypatch.setenv('SHOPIFY_CLIENT_SECRET', 'shpss_xyz')
        monkeypatch.setenv('WOO_BASE_URL', 'https://example.com')
        monkeypatch.setenv('WOO_CK', 'ck_abc')
        monkeypatch.setenv('WOO_CS', 'cs_abc')
        monkeypatch.delenv('DEEPL_API_KEY', raising=False)
        monkeypatch.delenv('TELEGRAM_BOT_TOKEN', raising=False)
        monkeypatch.delenv('TELEGRAM_CHAT_ID', raising=False)

        result = validate_secrets('production')

        assert result['passed'] is True
        assert len(result['warnings']) > 0


class TestFormatValidation:
    def test_shopify_access_token_must_start_with_shpat(self, monkeypatch):
        monkeypatch.setenv('GOOGLE_SERVICE_JSON_B64', 'dGVzdA==')
        monkeypatch.setenv('GOOGLE_SHEET_ID', 'sheet_id')
        monkeypatch.setenv('SHOPIFY_SHOP', 'shop.myshopify.com')
        monkeypatch.setenv('SHOPIFY_ACCESS_TOKEN', 'invalid_token_format')
        monkeypatch.setenv('SHOPIFY_CLIENT_SECRET', 'shpss_xyz')

        result = validate_secrets('staging')

        assert result['passed'] is False
        assert any('SHOPIFY_ACCESS_TOKEN' in e and 'format' in e for e in result['errors'])

    def test_shopify_client_secret_must_start_with_shpss(self, monkeypatch):
        monkeypatch.setenv('GOOGLE_SERVICE_JSON_B64', 'dGVzdA==')
        monkeypatch.setenv('GOOGLE_SHEET_ID', 'sheet_id')
        monkeypatch.setenv('SHOPIFY_SHOP', 'shop.myshopify.com')
        monkeypatch.setenv('SHOPIFY_ACCESS_TOKEN', 'shpat_abc')
        monkeypatch.setenv('SHOPIFY_CLIENT_SECRET', 'bad_secret')

        result = validate_secrets('staging')

        assert result['passed'] is False
        assert any('SHOPIFY_CLIENT_SECRET' in e and 'format' in e for e in result['errors'])

    def test_valid_formats_pass(self, monkeypatch):
        monkeypatch.setenv('GOOGLE_SERVICE_JSON_B64', 'dGVzdA==')
        monkeypatch.setenv('GOOGLE_SHEET_ID', 'sheet_id')
        monkeypatch.setenv('SHOPIFY_SHOP', 'shop.myshopify.com')
        monkeypatch.setenv('SHOPIFY_ACCESS_TOKEN', 'shpat_validtoken123')
        monkeypatch.setenv('SHOPIFY_CLIENT_SECRET', 'shpss_validsecret456')

        result = validate_secrets('staging')

        assert result['passed'] is True
        assert result['errors'] == []

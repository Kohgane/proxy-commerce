"""tests/test_config_schema.py — ConfigSchema 단위 테스트."""


class TestGetAllConfigSchema:
    """get_all_config_schema() 테스트."""

    def test_get_all_config_schema_returns_list(self):
        """get_all_config_schema()는 비어있지 않은 리스트를 반환한다."""
        from src.config.schema import get_all_config_schema
        schema = get_all_config_schema()

        assert isinstance(schema, list)
        assert len(schema) > 0

    def test_schema_entries_have_required_fields(self):
        """각 스키마 항목에 필수 키(name, type, default, required, description)가 있다."""
        from src.config.schema import get_all_config_schema
        schema = get_all_config_schema()

        required_keys = {'name', 'type', 'default', 'required', 'description'}
        for entry in schema:
            missing = required_keys - set(entry.keys())
            assert not missing, f"스키마 항목 {entry.get('name')} 에 누락된 키: {missing}"

    def test_schema_entries_have_valid_types(self):
        """각 스키마 항목의 type은 str/int/float/bool 중 하나이다."""
        from src.config.schema import get_all_config_schema
        schema = get_all_config_schema()

        valid_types = {str, int, float, bool}
        for entry in schema:
            assert entry['type'] in valid_types, \
                f"{entry['name']} 의 type={entry['type']} 이 유효하지 않음"

    def test_schema_entries_required_is_bool(self):
        """각 스키마 항목의 required 필드는 bool 타입이다."""
        from src.config.schema import get_all_config_schema
        schema = get_all_config_schema()

        for entry in schema:
            assert isinstance(entry['required'], bool), \
                f"{entry['name']}.required 가 bool이 아님: {entry['required']!r}"

    def test_schema_returns_copy(self):
        """get_all_config_schema()는 매번 새 리스트를 반환한다 (원본 보호)."""
        from src.config.schema import get_all_config_schema
        schema1 = get_all_config_schema()
        schema2 = get_all_config_schema()

        assert schema1 is not schema2


class TestGetSchemaByName:
    """get_schema_by_name() 테스트."""

    def test_get_schema_by_name_found(self):
        """존재하는 이름으로 조회 시 해당 항목이 반환된다."""
        from src.config.schema import get_schema_by_name
        entry = get_schema_by_name('GOOGLE_SHEET_ID')

        assert entry is not None
        assert entry['name'] == 'GOOGLE_SHEET_ID'

    def test_get_schema_by_name_not_found(self):
        """존재하지 않는 이름으로 조회 시 None이 반환된다."""
        from src.config.schema import get_schema_by_name
        result = get_schema_by_name('NONEXISTENT_KEY_XYZ_ABCDEF')

        assert result is None

    def test_get_schema_by_name_port(self):
        """PORT 스키마 항목이 int 타입이다."""
        from src.config.schema import get_schema_by_name
        entry = get_schema_by_name('PORT')

        assert entry is not None
        assert entry['type'] is int
        assert entry['default'] == 8000


class TestSchemaKeyEntries:
    """핵심 설정 항목 존재 여부 테스트."""

    def test_schema_has_google_sheet_id(self):
        """GOOGLE_SHEET_ID 항목이 스키마에 존재한다."""
        from src.config.schema import get_schema_by_name
        entry = get_schema_by_name('GOOGLE_SHEET_ID')
        assert entry is not None
        assert entry['required'] is True

    def test_schema_has_shopify_shop(self):
        """SHOPIFY_SHOP 항목이 스키마에 존재한다."""
        from src.config.schema import get_schema_by_name
        entry = get_schema_by_name('SHOPIFY_SHOP')
        assert entry is not None
        assert entry['group'] == 'shopify'

    def test_schema_has_config_management_entries(self):
        """설정 관리 항목(CONFIG_*)이 스키마에 존재한다."""
        from src.config.schema import get_schema_by_name

        for key in ('CONFIG_HOT_RELOAD_ENABLED', 'CONFIG_CHECK_INTERVAL', 'CONFIG_STRICT_VALIDATION'):
            entry = get_schema_by_name(key)
            assert entry is not None, f"{key} 이 스키마에 없음"

    def test_schema_has_telegram_entries(self):
        """Telegram 관련 항목이 스키마에 존재한다."""
        from src.config.schema import get_schema_by_name

        for key in ('TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID'):
            entry = get_schema_by_name(key)
            assert entry is not None, f"{key} 이 스키마에 없음"
            assert entry['group'] == 'telegram'

    def test_schema_groups_are_strings(self):
        """모든 스키마 항목의 group은 문자열이다."""
        from src.config.schema import get_all_config_schema
        schema = get_all_config_schema()

        for entry in schema:
            assert isinstance(entry.get('group', ''), str), \
                f"{entry['name']}.group 이 문자열이 아님"

"""tests/test_config_manager.py — ConfigManager 단위 테스트."""

import pytest


@pytest.fixture(autouse=True)
def reset_config_manager():
    """각 테스트 후 ConfigManager 싱글톤을 리셋한다."""
    yield
    from src.config.manager import ConfigManager
    ConfigManager._reset_instance()


class TestConfigManagerGet:
    """ConfigManager.get() 메서드 테스트."""

    def test_get_returns_env_value(self, monkeypatch):
        """환경변수가 설정된 경우 해당 값을 반환한다."""
        monkeypatch.setenv('GOOGLE_SHEET_ID', 'my_sheet_id_123')

        from src.config.manager import ConfigManager
        mgr = ConfigManager()
        assert mgr.get('GOOGLE_SHEET_ID') == 'my_sheet_id_123'

    def test_get_returns_default(self, monkeypatch):
        """환경변수가 설정되지 않은 경우 default 파라미터를 반환한다."""
        monkeypatch.delenv('UNKNOWN_CONFIG_KEY_XYZ', raising=False)

        from src.config.manager import ConfigManager
        mgr = ConfigManager()
        result = mgr.get('UNKNOWN_CONFIG_KEY_XYZ', default='fallback')
        assert result == 'fallback'

    def test_get_type_coercion_int(self, monkeypatch):
        """PORT 환경변수가 int로 변환되어 반환된다."""
        monkeypatch.setenv('PORT', '9090')

        from src.config.manager import ConfigManager
        mgr = ConfigManager()
        result = mgr.get('PORT')
        assert result == 9090
        assert isinstance(result, int)

    def test_get_type_coercion_bool(self, monkeypatch):
        """bool 타입 환경변수가 올바르게 변환된다."""
        monkeypatch.setenv('CONFIG_HOT_RELOAD_ENABLED', '1')

        from src.config.manager import ConfigManager
        mgr = ConfigManager()
        result = mgr.get('CONFIG_HOT_RELOAD_ENABLED')
        assert result is True


class TestConfigManagerReload:
    """ConfigManager.reload() 메서드 테스트."""

    def test_reload_picks_up_changes(self, monkeypatch):
        """환경변수 변경 후 reload() 호출 시 새 값을 반환한다."""
        monkeypatch.setenv('CONFIG_HOT_RELOAD_ENABLED', '1')
        monkeypatch.setenv('APP_ENV', 'development')

        from src.config.manager import ConfigManager
        mgr = ConfigManager()
        assert mgr.get('APP_ENV') == 'development'

        monkeypatch.setenv('APP_ENV', 'production')
        mgr.force_reload()  # force_reload는 항상 재로드

        assert mgr.get('APP_ENV') == 'production'

    def test_reload_disabled_when_hot_reload_off(self, monkeypatch):
        """CONFIG_HOT_RELOAD_ENABLED=0 시 reload()가 False를 반환한다."""
        monkeypatch.setenv('CONFIG_HOT_RELOAD_ENABLED', '0')

        from src.config.manager import ConfigManager
        mgr = ConfigManager()
        result = mgr.reload()

        assert result is False

    def test_reload_enabled_when_hot_reload_on(self, monkeypatch):
        """CONFIG_HOT_RELOAD_ENABLED=1 시 reload()가 True를 반환한다."""
        monkeypatch.setenv('CONFIG_HOT_RELOAD_ENABLED', '1')

        from src.config.manager import ConfigManager
        mgr = ConfigManager()
        result = mgr.reload()

        assert result is True


class TestConfigManagerOnChange:
    """ConfigManager.on_change() 콜백 테스트."""

    def test_on_change_callback_called(self, monkeypatch):
        """값이 변경될 때 등록된 콜백이 호출된다."""
        monkeypatch.setenv('APP_ENV', 'development')

        from src.config.manager import ConfigManager
        mgr = ConfigManager()

        called_with = []

        def callback(key, old_val, new_val):
            called_with.append((key, old_val, new_val))

        mgr.on_change('APP_ENV', callback)

        monkeypatch.setenv('APP_ENV', 'staging')
        mgr.force_reload()

        assert len(called_with) == 1
        assert called_with[0][0] == 'APP_ENV'
        assert called_with[0][2] == 'staging'

    def test_on_change_callback_not_called_when_no_change(self, monkeypatch):
        """값이 변경되지 않으면 콜백이 호출되지 않는다."""
        monkeypatch.setenv('APP_ENV', 'development')

        from src.config.manager import ConfigManager
        mgr = ConfigManager()

        called = []
        mgr.on_change('APP_ENV', lambda k, o, n: called.append((k, o, n)))

        # 동일한 값으로 재로드
        mgr.force_reload()

        assert len(called) == 0


class TestConfigManagerSingleton:
    """ConfigManager 싱글톤 테스트."""

    def test_singleton(self):
        """get_instance()는 동일한 인스턴스를 반환한다."""
        from src.config.manager import ConfigManager
        inst1 = ConfigManager.get_instance()
        inst2 = ConfigManager.get_instance()
        assert inst1 is inst2

    def test_reset_creates_new_instance(self):
        """_reset_instance() 후 get_instance()는 새 인스턴스를 반환한다."""
        from src.config.manager import ConfigManager
        inst1 = ConfigManager.get_instance()
        ConfigManager._reset_instance()
        inst2 = ConfigManager.get_instance()
        assert inst1 is not inst2

"""tests/test_config_watcher.py — FileWatcher 단위 테스트."""

from unittest.mock import MagicMock, patch


class TestFileWatcherDetection:
    """FileWatcher 파일 변경 감지 테스트."""

    def test_watcher_detects_change(self, tmp_path):
        """파일 mtime 변경 시 ConfigManager.force_reload()가 호출된다."""
        config_file = tmp_path / "config.yml"
        config_file.write_text("app_env: development\n")

        mock_mgr = MagicMock()

        with patch('src.config.manager.ConfigManager') as MockCM:
            MockCM.get_instance.return_value = mock_mgr

            from src.config.watcher import FileWatcher
            watcher = FileWatcher(config_file=str(config_file), interval=1)
            watcher._last_mtime = watcher._get_mtime() - 1  # 이전 mtime으로 설정

            # 강제로 변경 체크 실행
            watcher._check_and_reload()

        mock_mgr.force_reload.assert_called_once()

    def test_watcher_no_change(self, tmp_path):
        """mtime 변경이 없으면 reload가 호출되지 않는다."""
        config_file = tmp_path / "config.yml"
        config_file.write_text("app_env: development\n")

        mock_mgr = MagicMock()

        with patch('src.config.manager.ConfigManager') as MockCM:
            MockCM.get_instance.return_value = mock_mgr

            from src.config.watcher import FileWatcher
            watcher = FileWatcher(config_file=str(config_file), interval=1)
            # 현재 mtime으로 설정 (변경 없음)
            watcher._last_mtime = watcher._get_mtime()

            watcher._check_and_reload()

        mock_mgr.force_reload.assert_not_called()

    def test_watcher_file_not_exist(self):
        """파일이 존재하지 않으면 mtime이 0.0을 반환한다."""
        from src.config.watcher import FileWatcher
        watcher = FileWatcher(config_file="/nonexistent/path/config.yml", interval=5)
        assert watcher._get_mtime() == 0.0


class TestFileWatcherStartStop:
    """FileWatcher start/stop 테스트."""

    def test_watcher_stop(self, tmp_path):
        """stop() 호출 시 감시 스레드가 중지된다."""
        config_file = tmp_path / "config.yml"
        config_file.write_text("app_env: test\n")

        with patch('src.config.manager.ConfigManager'):
            from src.config.watcher import FileWatcher
            watcher = FileWatcher(config_file=str(config_file), interval=60)
            watcher.start()

            assert watcher.is_alive() is True

            watcher.stop()

            assert watcher.is_alive() is False

    def test_watcher_start_creates_daemon_thread(self, tmp_path):
        """start() 호출 시 daemon 스레드가 생성된다."""
        config_file = tmp_path / "config.yml"
        config_file.write_text("app_env: test\n")

        with patch('src.config.manager.ConfigManager'):
            from src.config.watcher import FileWatcher
            watcher = FileWatcher(config_file=str(config_file), interval=60)
            watcher.start()

            assert watcher._thread is not None
            assert watcher._thread.daemon is True

            watcher.stop()

    def test_watcher_double_start(self, tmp_path):
        """start()를 두 번 호출해도 스레드가 하나만 실행된다."""
        config_file = tmp_path / "config.yml"
        config_file.write_text("app_env: test\n")

        with patch('src.config.manager.ConfigManager'):
            from src.config.watcher import FileWatcher
            watcher = FileWatcher(config_file=str(config_file), interval=60)
            watcher.start()
            thread1 = watcher._thread
            watcher.start()  # 두 번째 호출 — 무시됨
            thread2 = watcher._thread

            assert thread1 is thread2

            watcher.stop()


class TestFileWatcherInterval:
    """FileWatcher interval 설정 테스트."""

    def test_watcher_default_interval(self, monkeypatch):
        """CONFIG_CHECK_INTERVAL 환경변수가 interval로 사용된다."""
        monkeypatch.setenv('CONFIG_CHECK_INTERVAL', '120')

        from src.config.watcher import FileWatcher
        watcher = FileWatcher(config_file="config.yml")
        assert watcher._interval == 120

    def test_watcher_explicit_interval(self):
        """명시적 interval 파라미터가 우선 적용된다."""
        from src.config.watcher import FileWatcher
        watcher = FileWatcher(config_file="config.yml", interval=30)
        assert watcher._interval == 30

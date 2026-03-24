"""src/config/watcher.py — 설정 파일 변경 감시기.

config.yml 파일의 mtime 변경을 주기적으로 확인하여
ConfigManager.reload()를 트리거한다.

환경변수:
  CONFIG_CHECK_INTERVAL — 파일 확인 주기 (초, 기본 60)
"""

import logging
import os
import threading

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_FILE = "config.yml"
_DEFAULT_INTERVAL = 60


class FileWatcher:
    """설정 파일 변경 감시기.

    daemon 스레드로 주기적으로 파일 mtime을 확인하고,
    변경이 감지되면 ConfigManager.get_instance().reload()를 호출한다.
    """

    def __init__(self, config_file: str = None, interval: int = None):
        """
        config_file: 감시할 파일 경로 (None이면 config.yml)
        interval: 확인 주기 (초, None이면 CONFIG_CHECK_INTERVAL 또는 60)
        """
        self._config_file = config_file or _DEFAULT_CONFIG_FILE
        self._interval = interval or int(os.getenv("CONFIG_CHECK_INTERVAL", str(_DEFAULT_INTERVAL)))
        self._last_mtime: float = 0.0
        self._stop_event = threading.Event()
        self._thread: threading.Thread = None

    def start(self) -> None:
        """파일 감시 daemon 스레드를 시작한다."""
        if self._thread and self._thread.is_alive():
            logger.debug("FileWatcher 이미 실행 중")
            return

        self._stop_event.clear()
        self._last_mtime = self._get_mtime()
        self._thread = threading.Thread(
            target=self._watch_loop,
            name="config-file-watcher",
            daemon=True,
        )
        self._thread.start()
        logger.info("FileWatcher 시작: file=%s interval=%ds", self._config_file, self._interval)

    def stop(self) -> None:
        """파일 감시 스레드를 중지한다."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=self._interval + 1)
        logger.info("FileWatcher 중지")

    def is_alive(self) -> bool:
        """감시 스레드가 실행 중인지 확인한다."""
        return self._thread is not None and self._thread.is_alive()

    # ── 내부 헬퍼 ───────────────────────────────────────────

    def _watch_loop(self) -> None:
        """주기적으로 파일 mtime을 확인하고 변경 시 reload를 호출한다."""
        while not self._stop_event.is_set():
            self._stop_event.wait(timeout=self._interval)
            if self._stop_event.is_set():
                break
            self._check_and_reload()

    def _check_and_reload(self) -> None:
        """파일 mtime을 확인하고 변경 시 ConfigManager를 재로드한다."""
        current_mtime = self._get_mtime()
        if current_mtime != self._last_mtime and current_mtime > 0:
            logger.info("설정 파일 변경 감지: %s (mtime=%s)", self._config_file, current_mtime)
            self._last_mtime = current_mtime
            try:
                from .manager import ConfigManager
                ConfigManager.get_instance().force_reload()
                logger.info("ConfigManager 재로드 완료")
            except Exception as exc:
                logger.warning("ConfigManager 재로드 실패: %s", exc)

    def _get_mtime(self) -> float:
        """파일의 수정 시간을 반환한다. 파일이 없으면 0.0."""
        try:
            return os.path.getmtime(self._config_file)
        except OSError:
            return 0.0

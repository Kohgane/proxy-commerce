"""src/config/manager.py — 설정 관리자 (싱글톤).

환경변수 + config.yml 파일에서 설정을 읽고, 변경 감지 콜백을 지원한다.

환경변수:
  CONFIG_HOT_RELOAD_ENABLED — hot-reload 활성화 여부 (기본 0)
"""

import logging
import os
import threading
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)

_YAML_AVAILABLE = False
try:
    import yaml
    _YAML_AVAILABLE = True
except ImportError:
    pass


class ConfigManager:
    """설정 관리자 싱글톤.

    환경변수와 config.yml 파일에서 설정을 통합 관리한다.
    변경 감지 콜백을 등록하여 설정 변경 시 알림을 받을 수 있다.
    """

    _instance: "ConfigManager" = None
    _lock: threading.Lock = threading.Lock()

    def __init__(self, config_file: str = None):
        """
        config_file: config.yml 파일 경로 (None이면 자동 탐색)
        """
        self._config_file = config_file or self._find_config_file()
        self._data: Dict[str, Any] = {}
        self._callbacks: Dict[str, List[Callable]] = {}
        self._callbacks_lock = threading.Lock()
        self._load()

    # ── 싱글톤 접근 ─────────────────────────────────────────

    @classmethod
    def get_instance(cls) -> "ConfigManager":
        """싱글톤 인스턴스를 반환한다."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def _reset_instance(cls) -> None:
        """테스트 목적으로 싱글톤을 초기화한다."""
        with cls._lock:
            cls._instance = None

    # ── 공개 API ────────────────────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        """설정 값을 반환한다. 스키마에 타입이 정의된 경우 변환한다.

        우선순위: 환경변수 > config.yml > 스키마 기본값 > default 파라미터
        """
        from .schema import get_schema_by_name

        raw = self._data.get(key)
        if raw is None:
            raw = default

        schema = get_schema_by_name(key)
        if schema and raw is not None:
            try:
                raw = self._coerce(raw, schema["type"])
            except (ValueError, TypeError):
                logger.warning("설정 타입 변환 실패: key=%s value=%r type=%s", key, raw, schema["type"])

        return raw

    def reload(self) -> bool:
        """설정을 재로드한다. 변경된 키에 대해 콜백을 호출한다.

        Returns:
            hot-reload가 활성화된 경우 True, 비활성화된 경우 False
        """
        hot_reload = os.getenv("CONFIG_HOT_RELOAD_ENABLED", "0") in ("1", "true", "True")
        if not hot_reload:
            logger.debug("CONFIG_HOT_RELOAD_ENABLED 비활성화 — 재로드 건너뜀")
            return False

        old_data = dict(self._data)
        self._load()
        self._notify_changes(old_data, self._data)
        return True

    def force_reload(self) -> None:
        """hot-reload 설정과 무관하게 강제로 재로드한다 (테스트/API 용도)."""
        old_data = dict(self._data)
        self._load()
        self._notify_changes(old_data, self._data)

    def on_change(self, key: str, callback: Callable[[str, Any, Any], None]) -> None:
        """특정 키 변경 시 호출될 콜백을 등록한다.

        Args:
            key: 감시할 환경변수 이름
            callback: callback(key, old_value, new_value) 형태의 함수
        """
        with self._callbacks_lock:
            if key not in self._callbacks:
                self._callbacks[key] = []
            self._callbacks[key].append(callback)

    def get_all(self) -> Dict[str, Any]:
        """현재 로드된 전체 설정 딕셔너리를 반환한다 (읽기 전용 복사본)."""
        return dict(self._data)

    # ── 내부 헬퍼 ───────────────────────────────────────────

    def _load(self) -> None:
        """환경변수 + config.yml에서 설정을 로드한다."""
        from .schema import get_all_config_schema

        data: Dict[str, Any] = {}

        # 1) 스키마 기본값 적용
        for entry in get_all_config_schema():
            if entry.get("default") is not None:
                data[entry["name"]] = entry["default"]

        # 2) config.yml 파일에서 평탄화된 키-값 로드
        if self._config_file and os.path.isfile(self._config_file) and _YAML_AVAILABLE:
            try:
                with open(self._config_file, "r", encoding="utf-8") as f:
                    yml = yaml.safe_load(f) or {}
                flat = self._flatten_yaml(yml)
                data.update(flat)
            except Exception as exc:
                logger.warning("config.yml 로드 실패: %s", exc)

        # 3) 환경변수가 최우선 (스키마에 있는 키만 + 기존 data 키 전체)
        all_keys = set(data.keys()) | {e["name"] for e in get_all_config_schema()}
        for key in all_keys:
            env_val = os.environ.get(key)
            if env_val is not None:
                data[key] = env_val

        self._data = data

    def _flatten_yaml(self, yml: dict, prefix: str = "") -> Dict[str, Any]:
        """중첩된 YAML을 UPPER_SNAKE_CASE 키로 평탄화한다."""
        result = {}
        for k, v in yml.items():
            full_key = f"{prefix}{k}".upper().replace("-", "_").replace(".", "_")
            if isinstance(v, dict):
                result.update(self._flatten_yaml(v, f"{full_key}_"))
            else:
                result[full_key] = v
        return result

    def _coerce(self, value: Any, typ: type) -> Any:
        """값을 지정한 타입으로 변환한다."""
        if isinstance(value, typ):
            return value
        if typ is bool:
            if isinstance(value, str):
                return value.lower() in ("1", "true", "yes", "on")
            return bool(value)
        if typ is int:
            return int(value)
        if typ is float:
            return float(value)
        return str(value)

    def _notify_changes(self, old: Dict[str, Any], new: Dict[str, Any]) -> None:
        """변경된 키에 대해 등록된 콜백을 호출한다."""
        all_keys = set(old.keys()) | set(new.keys())
        for key in all_keys:
            if old.get(key) != new.get(key):
                with self._callbacks_lock:
                    cbs = list(self._callbacks.get(key, []))
                for cb in cbs:
                    try:
                        cb(key, old.get(key), new.get(key))
                    except Exception as exc:
                        logger.warning("설정 변경 콜백 오류: key=%s exc=%s", key, exc)

    @staticmethod
    def _find_config_file() -> str:
        """프로젝트 루트의 config.yml 파일 경로를 탐색한다."""
        here = os.path.dirname(__file__)
        # src/config/ → src/ → project_root/
        candidates = [
            os.path.join(here, "..", "..", "config.yml"),
            os.path.join(here, "..", "..", "..", "config.yml"),
            "config.yml",
        ]
        for path in candidates:
            if os.path.isfile(os.path.abspath(path)):
                return os.path.abspath(path)
        return ""

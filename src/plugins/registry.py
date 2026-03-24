"""
플러그인 레지스트리 — 벤더 플러그인 등록/조회/자동 로드.

싱글톤 패턴으로 전역 레지스트리를 관리하며, @register_vendor 데코레이터와
load_plugins() 함수를 통해 플러그인을 등록한다.
"""

import importlib
import logging
import os
import pkgutil
from typing import Dict, List, Optional, Type

from .base import VendorPlugin

logger = logging.getLogger(__name__)


class PluginRegistry:
    """벤더 플러그인 싱글톤 레지스트리."""

    _instance: Optional["PluginRegistry"] = None
    _registry: Dict[str, Type[VendorPlugin]]

    def __new__(cls) -> "PluginRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._registry = {}
        return cls._instance

    # ── 등록 ─────────────────────────────────────────────────

    def register(self, plugin_cls: Type[VendorPlugin]) -> Type[VendorPlugin]:
        """플러그인 클래스를 레지스트리에 등록한다.

        인자:
            plugin_cls: VendorPlugin 서브클래스

        반환:
            등록된 플러그인 클래스 (데코레이터 패턴을 위해 원본 반환)

        예외:
            ValueError: name 속성이 비어있거나 VendorPlugin 서브클래스가 아닌 경우
        """
        if not issubclass(plugin_cls, VendorPlugin):
            raise ValueError(f"{plugin_cls!r} 는 VendorPlugin 서브클래스가 아닙니다.")
        if not plugin_cls.name:
            raise ValueError(f"{plugin_cls!r} 의 name 속성이 비어있습니다.")
        if plugin_cls.name in self._registry:
            logger.warning("플러그인 '%s' 이미 등록됨 — 덮어쓰기", plugin_cls.name)
        self._registry[plugin_cls.name] = plugin_cls
        logger.debug("플러그인 등록 완료: %s", plugin_cls.name)
        return plugin_cls

    # ── 조회 ─────────────────────────────────────────────────

    def get(self, name: str) -> Optional[Type[VendorPlugin]]:
        """이름으로 플러그인 클래스를 조회한다.

        인자:
            name: 벤더 고유 식별자

        반환:
            VendorPlugin 서브클래스 또는 None
        """
        return self._registry.get(name)

    def get_instance(self, name: str) -> Optional[VendorPlugin]:
        """이름으로 플러그인 인스턴스를 생성하여 반환한다.

        인자:
            name: 벤더 고유 식별자

        반환:
            VendorPlugin 인스턴스 또는 None
        """
        cls = self.get(name)
        return cls() if cls is not None else None

    def list_all(self) -> List[str]:
        """등록된 모든 플러그인 이름 목록을 반환한다."""
        return sorted(self._registry.keys())

    def list_plugins(self) -> List[dict]:
        """등록된 모든 플러그인의 메타데이터 목록을 반환한다."""
        result = []
        for name, cls in sorted(self._registry.items()):
            result.append({
                "name": name,
                "display_name": cls.display_name,
                "currency": cls.currency,
                "country": cls.country,
                "base_url": cls.base_url,
            })
        return result

    def is_registered(self, name: str) -> bool:
        """해당 이름의 플러그인이 등록되어 있는지 확인한다."""
        return name in self._registry

    # ── 초기화 ────────────────────────────────────────────────

    def clear(self) -> None:
        """레지스트리를 초기화한다. 주로 테스트에서 사용."""
        self._registry.clear()

    def __len__(self) -> int:
        return len(self._registry)

    def __repr__(self) -> str:
        return f"<PluginRegistry plugins={self.list_all()}>"


# 전역 레지스트리 인스턴스
_registry = PluginRegistry()


def register_vendor(cls: Type[VendorPlugin]) -> Type[VendorPlugin]:
    """벤더 플러그인 클래스 등록 데코레이터.

    사용 예::

        @register_vendor
        class MyVendorPlugin(VendorPlugin):
            name = "my_vendor"
            ...
    """
    return _registry.register(cls)


def load_plugins(vendors_dir: Optional[str] = None, config: Optional[dict] = None) -> int:
    """src/plugins/vendors/ 디렉토리에서 플러그인을 자동 로드한다.

    인자:
        vendors_dir: 플러그인 디렉토리 경로. None이면 기본 경로 사용.
        config: 설정 딕셔너리 (config.yml의 plugins.vendors 섹션).
                특정 벤더를 비활성화할 때 사용.

    반환:
        로드된 플러그인 수
    """
    plugins_enabled = int(os.getenv("PLUGINS_ENABLED", "1"))
    if not plugins_enabled:
        logger.info("PLUGINS_ENABLED=0 — 플러그인 자동 로드 건너뜀")
        return 0

    auto_load = int(os.getenv("PLUGINS_AUTO_LOAD", "1"))
    if not auto_load:
        logger.info("PLUGINS_AUTO_LOAD=0 — 플러그인 자동 로드 건너뜀")
        return 0

    if vendors_dir is None:
        vendors_dir = os.path.join(os.path.dirname(__file__), "vendors")

    loaded = 0
    for finder, module_name, _ in pkgutil.iter_modules([vendors_dir]):
        # 설정에서 비활성화된 벤더 스킵
        if config:
            vendor_key = module_name.replace("_plugin", "")
            vendor_cfg = config.get("vendors", {}).get(vendor_key, {})
            if not vendor_cfg.get("enabled", True):
                logger.info("벤더 '%s' 비활성화됨 (config) — 스킵", vendor_key)
                continue

        full_name = f"src.plugins.vendors.{module_name}"
        try:
            importlib.import_module(full_name)
            loaded += 1
            logger.debug("플러그인 모듈 로드: %s", full_name)
        except ImportError as exc:
            logger.error("플러그인 모듈 로드 실패: %s — %s", full_name, exc)

    logger.info("플러그인 자동 로드 완료: %d개", loaded)
    return loaded


def get_registry() -> PluginRegistry:
    """전역 PluginRegistry 인스턴스를 반환한다."""
    return _registry

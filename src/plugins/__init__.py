"""
src/plugins — 벤더 플러그인 시스템 패키지.

코드 수정 없이 설정만으로 새 소싱 벤더를 추가할 수 있는 플러그인 아키텍처.
"""

from .registry import PluginRegistry, register_vendor, load_plugins  # noqa: F401
from .base import VendorPlugin  # noqa: F401

__all__ = ["VendorPlugin", "PluginRegistry", "register_vendor", "load_plugins"]

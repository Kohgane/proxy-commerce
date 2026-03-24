"""
플러그인 검증 — 필수 메서드 존재 확인 및 반환 타입 검증.
"""

import logging
from typing import List, Tuple, Type

from .base import VendorPlugin

logger = logging.getLogger(__name__)

# 필수 메서드와 기대 반환 타입 매핑
_REQUIRED_METHODS: List[Tuple[str, type]] = [
    ("fetch_products", list),
    ("check_stock", bool),
    ("get_vendor_info", dict),
]

# 필수 메타데이터 속성
_REQUIRED_ATTRS = ["name", "display_name", "currency", "country", "base_url"]


def validate_plugin_class(plugin_cls: Type[VendorPlugin]) -> List[str]:
    """플러그인 클래스를 정적으로 검증한다.

    인자:
        plugin_cls: 검증할 VendorPlugin 서브클래스

    반환:
        오류 메시지 목록. 비어 있으면 검증 통과.
    """
    errors: List[str] = []

    # VendorPlugin 상속 여부 확인
    if not issubclass(plugin_cls, VendorPlugin):
        errors.append(f"{plugin_cls.__name__} 은 VendorPlugin 서브클래스가 아닙니다.")
        return errors  # 이후 검증 불가

    # 필수 메타데이터 속성 확인
    for attr in _REQUIRED_ATTRS:
        val = getattr(plugin_cls, attr, "")
        if not val:
            errors.append(f"'{attr}' 클래스 속성이 비어있습니다.")

    # 필수 메서드 구현 여부 확인
    for method_name, _ in _REQUIRED_METHODS:
        if not callable(getattr(plugin_cls, method_name, None)):
            errors.append(f"필수 메서드 '{method_name}' 가 구현되지 않았습니다.")

    return errors


def validate_plugin_instance(plugin: VendorPlugin) -> List[str]:
    """플러그인 인스턴스를 런타임 검증한다 (get_vendor_info 호출).

    인자:
        plugin: 검증할 VendorPlugin 인스턴스

    반환:
        오류 메시지 목록. 비어 있으면 검증 통과.
    """
    errors = validate_plugin_class(type(plugin))

    # get_vendor_info 반환값 검증
    try:
        info = plugin.get_vendor_info()
        if not isinstance(info, dict):
            errors.append(f"get_vendor_info() 가 dict 를 반환해야 하지만 {type(info).__name__} 를 반환했습니다.")
        else:
            for key in ("name", "currency", "country"):
                if key not in info:
                    errors.append(f"get_vendor_info() 반환값에 '{key}' 키가 없습니다.")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"get_vendor_info() 호출 중 오류: {exc}")

    return errors


def check_compatibility(plugin_cls: Type[VendorPlugin]) -> bool:
    """플러그인 호환성을 빠르게 체크한다.

    인자:
        plugin_cls: 확인할 VendorPlugin 서브클래스

    반환:
        호환 가능하면 True, 아니면 False
    """
    errors = validate_plugin_class(plugin_cls)
    if errors:
        logger.warning("플러그인 호환성 체크 실패 (%s): %s", plugin_cls.__name__, errors)
        return False
    return True

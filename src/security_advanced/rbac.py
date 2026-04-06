"""src/security_advanced/rbac.py — 역할 기반 접근 제어 (RBAC) (Phase 116)."""
from __future__ import annotations

import functools
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# ── 권한 상수 ────────────────────────────────────────────────────────────────

class Permission:
    PRODUCT_READ = "product:read"
    PRODUCT_WRITE = "product:write"
    PRODUCT_DELETE = "product:delete"
    ORDER_READ = "order:read"
    ORDER_WRITE = "order:write"
    ORDER_CANCEL = "order:cancel"
    INVENTORY_READ = "inventory:read"
    INVENTORY_WRITE = "inventory:write"
    ANALYTICS_READ = "analytics:read"
    ANALYTICS_EXPORT = "analytics:export"
    SETTINGS_READ = "settings:read"
    SETTINGS_WRITE = "settings:write"
    USER_MANAGE = "user:manage"
    ADMIN_FULL = "admin:full"

    ALL: Set[str] = {
        PRODUCT_READ, PRODUCT_WRITE, PRODUCT_DELETE,
        ORDER_READ, ORDER_WRITE, ORDER_CANCEL,
        INVENTORY_READ, INVENTORY_WRITE,
        ANALYTICS_READ, ANALYTICS_EXPORT,
        SETTINGS_READ, SETTINGS_WRITE,
        USER_MANAGE, ADMIN_FULL,
    }


# 내장 역할 정의
_BUILTIN_ROLES = {
    "super_admin": Permission.ALL,
    "admin": Permission.ALL - {Permission.ADMIN_FULL},
    "manager": {
        Permission.ORDER_READ, Permission.ORDER_WRITE, Permission.ORDER_CANCEL,
        Permission.INVENTORY_READ, Permission.INVENTORY_WRITE,
        Permission.ANALYTICS_READ, Permission.ANALYTICS_EXPORT,
        Permission.PRODUCT_READ,
    },
    "operator": {
        Permission.ORDER_READ, Permission.ORDER_WRITE,
        Permission.INVENTORY_READ, Permission.INVENTORY_WRITE,
        Permission.PRODUCT_READ,
    },
    "viewer": {
        Permission.PRODUCT_READ, Permission.ORDER_READ,
        Permission.INVENTORY_READ, Permission.ANALYTICS_READ,
        Permission.SETTINGS_READ,
    },
}


@dataclass
class Role:
    id: str
    name: str
    permissions: Set[str]
    description: str = ""
    is_system: bool = False


class PermissionDeniedError(Exception):
    """권한 없음 예외."""
    pass


class RBACManager:
    """역할 기반 접근 제어 관리자."""

    def __init__(self) -> None:
        self._roles: Dict[str, Role] = {}
        self._user_roles: Dict[str, Set[str]] = {}  # user_id -> set of role_ids
        self._initialize_builtin_roles()

    def _initialize_builtin_roles(self) -> None:
        for name, permissions in _BUILTIN_ROLES.items():
            role_id = f"builtin_{name}"
            self._roles[role_id] = Role(
                id=role_id,
                name=name,
                permissions=set(permissions),
                description=f"내장 역할: {name}",
                is_system=True,
            )

    # ── 역할 관리 ──────────────────────────────────────────────────────────

    def create_role(
        self,
        name: str,
        permissions: Set[str],
        description: str = "",
    ) -> Role:
        role_id = str(uuid.uuid4())
        role = Role(
            id=role_id,
            name=name,
            permissions=set(permissions),
            description=description,
            is_system=False,
        )
        self._roles[role_id] = role
        logger.info("역할 생성: %s (%s)", name, role_id)
        return role

    def delete_role(self, role_id: str) -> None:
        role = self._roles.get(role_id)
        if role is None:
            raise KeyError(f"역할을 찾을 수 없음: {role_id}")
        if role.is_system:
            raise ValueError(f"내장 역할은 삭제할 수 없음: {role.name}")
        del self._roles[role_id]
        # 사용자 역할 매핑에서도 제거
        for user_roles in self._user_roles.values():
            user_roles.discard(role_id)
        logger.info("역할 삭제: %s", role_id)

    def get_role(self, role_id: str) -> Optional[Role]:
        return self._roles.get(role_id)

    def get_role_by_name(self, name: str) -> Optional[Role]:
        for role in self._roles.values():
            if role.name == name:
                return role
        return None

    def list_roles(self) -> List[Role]:
        return list(self._roles.values())

    # ── 사용자 역할 할당/해제 ─────────────────────────────────────────────

    def assign_role(self, user_id: str, role_id: str) -> None:
        if role_id not in self._roles:
            raise KeyError(f"역할을 찾을 수 없음: {role_id}")
        if user_id not in self._user_roles:
            self._user_roles[user_id] = set()
        self._user_roles[user_id].add(role_id)
        logger.info("역할 할당: user=%s role=%s", user_id, role_id)

    def revoke_role(self, user_id: str, role_id: str) -> None:
        if user_id in self._user_roles:
            self._user_roles[user_id].discard(role_id)
        logger.info("역할 해제: user=%s role=%s", user_id, role_id)

    def get_user_roles(self, user_id: str) -> List[Role]:
        role_ids = self._user_roles.get(user_id, set())
        return [self._roles[rid] for rid in role_ids if rid in self._roles]

    def get_user_permissions(self, user_id: str) -> Set[str]:
        permissions: Set[str] = set()
        for role in self.get_user_roles(user_id):
            permissions |= role.permissions
        return permissions

    def check_permission(self, user_id: str, permission: str) -> bool:
        return permission in self.get_user_permissions(user_id)

    # ── @require_permission 데코레이터 ────────────────────────────────────

    def require_permission(self, permission: str) -> Callable:
        """권한 검사 데코레이터. 권한 없으면 PermissionDeniedError 발생."""
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args: Any, user_id: Optional[str] = None, **kwargs: Any) -> Any:
                if user_id is None:
                    raise PermissionDeniedError(f"user_id 필요: {permission}")
                if not self.check_permission(user_id, permission):
                    raise PermissionDeniedError(
                        f"권한 없음: user={user_id} permission={permission}"
                    )
                return func(*args, user_id=user_id, **kwargs)
            return wrapper
        return decorator

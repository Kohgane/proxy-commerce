"""src/feature_flags/feature_flag_manager.py — 피쳐 플래그 관리."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class FeatureFlagManager:
    """피쳐 플래그 CRUD."""

    def __init__(self) -> None:
        self._flags: Dict[str, dict] = {}

    def create_flag(self, name: str, enabled: bool = False, description: str = "") -> dict:
        if name in self._flags:
            raise ValueError(f"이미 존재하는 플래그: {name}")
        flag = {
            "name": name,
            "enabled": enabled,
            "description": description,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "rollout_strategy": None,
        }
        self._flags[name] = flag
        return dict(flag)

    def get_flag(self, name: str) -> Optional[dict]:
        flag = self._flags.get(name)
        return dict(flag) if flag else None

    def update_flag(self, name: str, **kwargs) -> dict:
        if name not in self._flags:
            raise KeyError(f"플래그 없음: {name}")
        for k, v in kwargs.items():
            if k not in ("name", "created_at"):
                self._flags[name][k] = v
        self._flags[name]["updated_at"] = _now_iso()
        return dict(self._flags[name])

    def delete_flag(self, name: str) -> None:
        if name not in self._flags:
            raise KeyError(f"플래그 없음: {name}")
        del self._flags[name]

    def list_flags(self) -> List[dict]:
        return [dict(f) for f in self._flags.values()]

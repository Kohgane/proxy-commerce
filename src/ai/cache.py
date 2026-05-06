"""src/ai/cache.py — AI 결과 캐시 (Phase 134).

Sheets `ai_cache` 워크시트에 캐시 저장.
TTL 30일. 동일 원문 재호출 시 비용 절약.
컬럼: cache_key | source_hash | result_json | provider | created_at | hits | tokens | cost_usd
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

_CACHE_TTL_DAYS = int(os.getenv("AI_CACHE_TTL_DAYS", "30"))


class AICache:
    """Google Sheets 기반 AI 결과 캐시."""

    WORKSHEET_NAME = "ai_cache"
    HEADERS = ["cache_key", "source_hash", "result_json", "provider", "created_at", "hits", "tokens", "cost_usd"]

    def __init__(self) -> None:
        self._ws = None

    def _get_ws(self):
        if self._ws is not None:
            return self._ws
        try:
            from src.utils.sheets import get_worksheet
            ws = get_worksheet(self.WORKSHEET_NAME, headers=self.HEADERS)
            self._ws = ws
            return ws
        except Exception as exc:
            logger.debug("ai_cache 워크시트 접근 불가: %s", exc)
            return None

    def get(self, cache_key: str) -> Optional[Any]:
        """캐시 조회. Hit 시 결과 반환, miss 시 None."""
        ws = self._get_ws()
        if ws is None:
            return None
        try:
            rows = ws.get_all_records()
            cutoff = datetime.now(timezone.utc) - timedelta(days=_CACHE_TTL_DAYS)
            for i, row in enumerate(rows):
                if row.get("cache_key") != cache_key:
                    continue
                created_str = str(row.get("created_at", ""))
                try:
                    created = datetime.fromisoformat(created_str)
                    if created.tzinfo is None:
                        created = created.replace(tzinfo=timezone.utc)
                    if created < cutoff:
                        logger.debug("ai_cache TTL 만료: %s", cache_key)
                        return None
                except Exception:
                    pass

                result_json = row.get("result_json", "")
                if not result_json:
                    return None
                try:
                    result = json.loads(result_json)
                    # 조회수(hits) 증가
                    self._increment_hits(ws, i + 2)  # 헤더 행 + 1-indexed
                    return result
                except json.JSONDecodeError:
                    return None
            return None
        except Exception as exc:
            logger.warning("ai_cache 조회 오류: %s", exc)
            return None

    def set(self, cache_key: str, result: Any, provider: str = "", tokens: int = 0, cost_usd: float = 0.0) -> None:
        """캐시 저장."""
        ws = self._get_ws()
        if ws is None:
            logger.debug("ai_cache 미연결 — 캐시 저장 건너뜀")
            return
        try:
            result_json = json.dumps(result, ensure_ascii=False, default=str)
            source_hash = hashlib.sha256(cache_key.encode()).hexdigest()[:16]
            now = datetime.now(timezone.utc).isoformat()
            row = [cache_key, source_hash, result_json, provider, now, "0", str(tokens), str(cost_usd)]
            ws.append_row(row)
            logger.debug("ai_cache 저장: %s", cache_key)
        except Exception as exc:
            logger.warning("ai_cache 저장 오류: %s", exc)

    def invalidate(self, cache_key: str) -> None:
        """캐시 무효화 (해당 키 행 삭제)."""
        ws = self._get_ws()
        if ws is None:
            return
        try:
            rows = ws.get_all_records()
            for i, row in enumerate(rows):
                if row.get("cache_key") == cache_key:
                    ws.delete_rows(i + 2)  # 헤더 행 + 1-indexed
                    break
        except Exception as exc:
            logger.warning("ai_cache 무효화 오류: %s", exc)

    def _increment_hits(self, ws, row_index: int) -> None:
        """조회수 증가."""
        try:
            # hits는 7번째 컬럼 (F)
            hits_col = self.HEADERS.index("hits") + 1
            current = ws.cell(row_index, hits_col).value
            try:
                new_hits = int(current or "0") + 1
            except ValueError:
                new_hits = 1
            ws.update_cell(row_index, hits_col, str(new_hits))
        except Exception as exc:
            logger.debug("ai_cache hits 증가 오류: %s", exc)

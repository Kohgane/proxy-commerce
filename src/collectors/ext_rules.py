"""F50 — 확장이 **재설치 없이** 받는 사이트 규칙(셀렉터·카드 탐지·타일 표시) — 데이터만.

정본은 `ext_rules.json` 한 파일. 서버는 그걸 그대로 서빙하고, 해시는 **정규화 JSON**
(`sort_keys` · `(",", ":")` 구분자 · 유니코드 그대로)의 sha256이다. 확장은 같은 규칙으로 해시를 다시 재서
맞을 때만 캐시한다(깨진 응답을 규칙으로 쓰지 않는다). 못 받거나 안 맞으면 번들(kgp-rules.js) 값.
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

RULES_PATH = Path(__file__).with_name("ext_rules.json")


def canonical(rules) -> str:
    return json.dumps(rules, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def rules_hash(rules) -> str:
    return hashlib.sha256(canonical(rules).encode("utf-8")).hexdigest()


@lru_cache(maxsize=1)
def load() -> dict:
    """`{version, hash, rules}` — 파일을 못 읽으면 예외(서빙 쪽이 정직하게 실패를 말한다)."""
    raw = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    rules = raw["rules"]
    return {"version": str(raw["version"]), "hash": rules_hash(rules), "rules": rules}

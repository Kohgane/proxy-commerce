"""Y11O-1(오너 2026-10-15) — 상품명 토큰으로 쿠팡 예측 리프를 바로잡는 규칙(`naver_category_map.json` `title_rules`).

실측: VRSUK 4ebaf1b8 「… 심플 리클라이너 오일 왁스 가죽 사무용 회전 승강 1인 의자」 — 쿠팡 예측 77989 「학생의자/사무용의자」.
오너: 라운지체어다. 상품명에 리클라이너·라운지·안락·오토만이 있으면 쿠팡 의자류 예측을 안락의자로 바로잡고, 네이버는
라운지 신호(원문 「躺椅」 등)가 있으면 의자>인테리어의자, 없으면 의자>안락의자.

- `coupang_fix(product, predicted_id)` → `{id, name, path, tokens, why}` 또는 None. 쿠팡 등록·사전검증·네이버 다리가 같이 쓴다.
- `naver_fix(product, coupang_id)` → `{id, alt, signals, why}` 또는 None.
- 오너가 「AI가 고쳤어요 — 쿠팡 카테고리」를 되돌리면 `coupang_category_no_override`(상품)로 규칙을 끈다.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

_FILE = Path(__file__).with_name("naver_category_map.json")
_CACHE: dict = {"mtime": None, "rules": []}


def rules() -> List[dict]:
    try:
        mt = _FILE.stat().st_mtime
        if _CACHE["mtime"] != mt:
            _CACHE.update(mtime=mt, rules=json.loads(_FILE.read_text(encoding="utf-8")).get("title_rules") or [])
    except Exception:                                             # noqa: BLE001
        return []
    return _CACHE["rules"]


def _title(p: dict) -> str:
    p = p or {}
    return " ".join(str(p.get(k) or "") for k in ("title_ko", "title", "coupang_name"))


def _wide(p: dict) -> str:
    """라운지 신호를 찾는 곳 — 상품명(한국어·원문)·검색어·규격·옵션 이름."""
    p = p or {}
    parts = [_title(p)] + [str(p.get(k) or "") for k in ("title_src", "title_en", "title_original", "category_text")]
    parts += [str(x) for x in list(p.get("keywords") or []) + list(p.get("tags") or [])]
    for kv in p.get("detail_specs") or []:
        if isinstance(kv, (list, tuple)):
            parts += [str(x) for x in kv]
    return " ".join(parts)


def _hits(text: str, words) -> List[str]:
    low = text.lower()
    return [w for w in words or [] if w and w.lower() in low]


def coupang_fix(product: dict, predicted_id: str) -> Optional[Dict[str, str]]:
    p = product or {}
    if p.get("coupang_category_no_override"):
        return None
    pid = str(predicted_id or "").strip()
    for r in rules():
        toks = _hits(_title(p), r.get("tokens"))
        if toks and _hits(_wide(p), r.get("absent")):
            continue                                               # Y15: 「없어야 하는」 신호가 있으면 이 규칙이 아니다
        if toks and pid in (r.get("coupang_from") or []) and pid != str(r.get("coupang")):
            return {"id": str(r["coupang"]), "name": r.get("coupang_name", ""), "path": r.get("coupang_path", ""),
                    "rule": r.get("key", ""), "tokens": toks, "from": pid,
                    "why": f"상품명 「{'·'.join(toks)}」 → {r.get('coupang_name', '')}"}
    return None


def naver_fix(product: dict, coupang_id: str) -> Optional[Dict]:
    p = product or {}
    cid = str(coupang_id or "").strip()
    for r in rules():
        toks = _hits(_title(p), r.get("tokens"))
        if not toks or cid not in set(r.get("coupang_from") or []) | {str(r.get("coupang"))}:
            continue
        if _hits(_wide(p), r.get("absent")):
            continue                                               # Y15: 빈백 신호가 있으면 진짜 빈백 — 매핑표 그대로
        sig = _hits(_wide(p), r.get("lounge_signals"))
        nid = str(r["naver_lounge"] if sig else r["naver"])
        other = str(r["naver"] if sig else r["naver_lounge"])
        alt = [other] + [str(a) for a in r.get("naver_alt") or [] if str(a) not in (nid, other)]
        if r.get("key") == "not_beanbag_sofa":
            why = f"상품명 「{'·'.join(toks)}」 · 빈백 신호 없음 → 빈백 아님(1인 소파 → 안락의자)"
        else:
            why = f"상품명 「{'·'.join(toks)}」" + (f" + 라운지 신호 「{'·'.join(sig)}」 → 라운지체어" if sig else " → 안락의자")
        return {"id": nid, "alt": alt, "signals": sig, "tokens": toks, "why": why}
    return None

"""오너 지시 2026-10-27 22:20 ①「각 유저의 서류/등록증/허가증을 받으면 가능하게」 — 셀러별 인증·허가 서류함.

- 저장: 운영 DB `app_state` `user_docs:{sid}` = `{"docs": [{id, kind, number, issuer, valid_until, note, created_at, deleted_at}]}`.
  지우기는 소프트(`deleted_at`) — 지운 서류는 게이트가 더 쓰지 않지만 기록은 남는다.
- 게이트(`risk_gate.scan(owner=…)`): `cert:` 보류 품목이 요구하는 종류(`risk_tokens.json` cert[].docs)의 서류가 그 셀러에게 있고
  유효기간 안이면 보류 → 주의(통과) · 결정 기록 `{"by": "user_doc", "doc_id": …}`. 없으면 보류 그대로 + 「서류 추가하면 자동 통과」.
- 서류 번호는 셀러 본인이 화면에서 넣는다(감독·CC가 임의로 넣지 않는다). 파일 첨부는 아직 없다 — 번호·발급기관·유효기간만.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone, timedelta
from typing import Dict, Iterable, List, Optional

PREFIX = "user_docs:"
KST = timezone(timedelta(hours=9))

# 종류 — 화면 선택지와 게이트가 같은 표를 본다
KINDS: Dict[str, str] = {
    "mfds_food": "건강기능식품 판매업 신고(식약처)",
    "import_license": "수입식품등 수입판매업 등록",
    "cosmetic": "화장품 책임판매업 등록",
    "kc": "KC 인증(전기·어린이제품)",
    "radio": "전파 적합성 평가(KC 전파)",
    "knife_license": "도검 판매업 허가(경찰청)",
    "other": "기타 허가·등록증",
}


def _st():
    from src.db import image_translate_queue_pg as st
    return st


def _today() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def _clean_date(v) -> str:
    s = str(v or "").strip()[:10]
    if not s:
        return ""
    try:
        datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        raise ValueError("유효기간은 YYYY-MM-DD 형식으로 넣어 주세요 (없으면 비워 두세요)")
    return s


def _rows(sid: str) -> List[dict]:
    return [d for d in (_st().state_get(PREFIX + str(sid)) or {}).get("docs") or [] if isinstance(d, dict)]


def list_docs(sid: str, *, include_deleted: bool = False) -> List[dict]:
    """한 셀러의 서류 — 화면용 `status`(유효·만료·삭제) 붙여서. 최신 먼저."""
    out = []
    today = _today()
    for d in _rows(sid):
        if d.get("deleted_at") and not include_deleted:
            continue
        exp = str(d.get("valid_until") or "")
        status = "deleted" if d.get("deleted_at") else ("expired" if exp and exp < today else "valid")
        out.append(dict(d, status=status, kind_label=KINDS.get(str(d.get("kind")), str(d.get("kind") or ""))))
    return sorted(out, key=lambda d: str(d.get("created_at") or ""), reverse=True)


def add_doc(sid: str, *, kind: str, number: str, issuer: str = "", valid_until: str = "", note: str = "") -> dict:
    kind = str(kind or "").strip()
    if kind not in KINDS:
        raise ValueError("서류 종류를 골라 주세요")
    number = str(number or "").strip()
    if not number:
        raise ValueError("서류 번호(신고·등록·인증 번호)를 넣어 주세요")
    doc = {"id": secrets.token_hex(6), "kind": kind, "number": number[:80], "issuer": str(issuer or "").strip()[:80],
           "valid_until": _clean_date(valid_until), "note": str(note or "").strip()[:200],
           "created_at": datetime.now(timezone.utc).isoformat(), "deleted_at": ""}
    _st().state_update(PREFIX + str(sid), lambda cur: {"docs": list(cur.get("docs") or []) + [doc]})
    return doc


def delete_doc(sid: str, doc_id: str) -> bool:
    """소프트 삭제 — 지운 서류는 게이트가 쓰지 않는다. 지웠으면 True."""
    hit = {"ok": False}

    def _fn(cur):
        docs = []
        for d in cur.get("docs") or []:
            if isinstance(d, dict) and d.get("id") == doc_id and not d.get("deleted_at"):
                d = dict(d, deleted_at=datetime.now(timezone.utc).isoformat())
                hit["ok"] = True
            docs.append(d)
        return {"docs": docs}
    _st().state_update(PREFIX + str(sid), _fn)
    return hit["ok"]


def valid_doc_for(owner: Iterable[str], kinds: Iterable[str]) -> Optional[dict]:
    """`owner`(그 셀러의 정체성들) 중 누군가에게 `kinds` 중 하나의 유효한(만료 전 · 안 지운) 서류가 있으면 그 서류."""
    want = {str(k) for k in kinds or [] if k}
    if not want:
        return None
    for sid in {str(s) for s in owner or [] if s}:
        for d in list_docs(sid):
            if d["status"] == "valid" and str(d.get("kind")) in want:
                return dict(d, sid=sid)
    return None


def all_docs(limit: int = 500) -> List[dict]:
    """관리자 열람 — 전 셀러의 서류(지운 것 포함)."""
    out = []
    for key, _v in _st().state_scan(PREFIX, limit=limit):
        sid = key[len(PREFIX):]
        for d in list_docs(sid, include_deleted=True):
            out.append(dict(d, sid=sid))
    return sorted(out, key=lambda d: str(d.get("created_at") or ""), reverse=True)

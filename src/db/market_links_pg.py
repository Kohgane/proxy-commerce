"""src/db/market_links_pg.py — 마켓 연동정보(자격증명) Postgres 백엔드(이관 2단계).

market_credentials의 저장을 data/<seller>.json(Render ephemeral) → PG(영속)로. 값은 앱이
Fernet으로 암호화한 뒤 enc_blob(암호화 컬럼)에 저장 — DB엔 암호문만. 복호화 키 없으면 평문
JSON(is_encrypted=false, 개발용)로 저장하되 경고(market_credentials가 담당).

market_credentials가 fernet/필드 정제를 담당하고, 이 모듈은 (user_id, market)별 blob 저장·조회만.
"""
from __future__ import annotations

import json
import logging

from . import pg

logger = logging.getLogger(__name__)


def _encode(values: dict):
    """values dict → (enc_blob, is_encrypted). 키 있으면 Fernet 암호문, 없으면 평문 JSON."""
    from src.seller_console import market_credentials as mc
    raw = json.dumps(values or {}, ensure_ascii=False)
    fernet = mc._fernet()
    if fernet:
        return fernet.encrypt(raw.encode("utf-8")).decode("utf-8"), True
    logger.warning("암호화 키 없음 — 마켓 자격증명을 평문으로 저장(개발용). MARKET_CRED_ENC_KEY 설정 권장.")
    return raw, False


def _decode(enc_blob: str, is_encrypted: bool) -> dict:
    try:
        if is_encrypted:
            from src.seller_console import market_credentials as mc
            fernet = mc._fernet()
            if not fernet:
                logger.warning("암호화된 자격증명이나 복호화 키 없음 — 빈 값")
                return {}
            raw = fernet.decrypt(str(enc_blob or "").encode()).decode("utf-8")
        else:
            raw = enc_blob or "{}"
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning("자격증명 복호화 실패: %s", exc)
        return {}


def load_all(seller_id: str) -> dict:
    """{market: {env: value}} — 셀러의 모든 마켓 연동정보."""
    out = {}
    with pg.query() as cur:
        cur.execute("SELECT market, enc_blob, is_encrypted FROM market_links WHERE user_id=%s AND deleted_at IS NULL",
                    (str(seller_id or ""),))
        for market, enc_blob, is_enc in cur.fetchall():
            out[market] = _decode(enc_blob, is_enc)
    return out


def get(seller_id: str, market: str) -> dict:
    with pg.query() as cur:
        cur.execute("SELECT enc_blob, is_encrypted FROM market_links WHERE user_id=%s AND market=%s AND deleted_at IS NULL LIMIT 1",
                    (str(seller_id or ""), market))
        r = cur.fetchone()
        return _decode(r[0], r[1]) if r else {}


def save(seller_id: str, market: str, merged: dict) -> dict:
    """(user_id, market) upsert — 커밋 후에만 성공(영속). merged=최종 저장값(정제·병합 완료)."""
    enc_blob, is_enc = _encode(merged)
    with pg.tx() as cur:
        cur.execute(
            """INSERT INTO market_links (user_id, market, enc_blob, is_encrypted)
               VALUES (%s,%s,%s,%s)
               ON CONFLICT (user_id, market) WHERE deleted_at IS NULL
               DO UPDATE SET enc_blob=EXCLUDED.enc_blob, is_encrypted=EXCLUDED.is_encrypted""",
            (str(seller_id or ""), market, enc_blob, is_enc))
    return dict(merged)


def delete(seller_id: str, market: str) -> bool:
    with pg.tx() as cur:
        cur.execute("UPDATE market_links SET deleted_at=now() WHERE user_id=%s AND market=%s AND deleted_at IS NULL RETURNING id",
                    (str(seller_id or ""), market))
        return cur.fetchone() is not None

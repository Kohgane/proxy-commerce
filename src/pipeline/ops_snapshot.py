"""src/pipeline/ops_snapshot.py — Stage 6-a 대시보드가 읽는 **운영 스냅샷**.

집계를 **새로 만들지 않는다**(오너 G3 — 발명 0). 이미 있는 산출만 모아 온다:

  · 계정 상태  → `coupang_replicate._account_creds` / `NaverSmartStoreUploader` 자격 판별(둘 다 기존)
  · 등록 대장  → `market_registrations.counts()` / `watch_queue()`(P4 크론이 쓰는 그 소스)
  · 소싱 큐    → `collect_history_store.summary()`(수집 이력 요약, 기존)

**정직 규율:** 소스가 미연결이면 숫자를 만들지 않고 `connected=False` + 사유를 올린다.
화면은 그 자리에 "미연결"을 찍는다 — 0을 찍으면 "0건"과 구분이 안 된다(가짜 수치 금지).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# 4계정 축 — 쿠팡(고가네·우주대행)과 스마트스토어(chezgoga·gocosmos)는 **다른 축**이다.
ACCOUNT_AXES = (
    ("coupang", "쿠팡", ("gogane", "woojoo")),
    ("smartstore", "스마트스토어", ("chezgoga", "gocosmos")),
)


def _coupang_account(account: str) -> dict:
    """쿠팡 계정 1개 상태. 자격 판별은 기존 `_account_creds`가 정본(재구현 0)."""
    try:
        from src.pipeline.coupang_replicate import COUPANG_ACCOUNTS, _account_creds
        meta = COUPANG_ACCOUNTS.get(account) or {}
        access, secret, vendor = _account_creds(account)
        ready = bool(access and secret)
        return {"account": account, "label": meta.get("label") or account,
                "vendor_id": vendor or meta.get("vendor_id", ""),
                "connected": ready,
                "note": "" if ready else "API 자격 미설정"}
    except Exception as exc:                       # 스냅샷이 대시보드를 죽이지 않게
        logger.warning('쿠팡 계정 상태 조회 실패(%s): %s', account, exc)
        return {"account": account, "label": account, "vendor_id": "",
                "connected": False, "note": "상태 조회 실패"}


def _smartstore_account(account: str) -> dict:
    """스마트스토어 계정 1개 상태. 자격은 업로더가 읽는 그 env가 정본."""
    try:
        from src.uploaders.naver_uploader import NaverSmartStoreUploader
        up = NaverSmartStoreUploader(account=account)
        ready = bool(up.client_id and up.client_secret)
        return {"account": account, "label": account, "vendor_id": "",
                "connected": ready,
                "note": "" if ready else "API 자격 미설정"}
    except Exception as exc:
        logger.warning('스마트스토어 계정 상태 조회 실패(%s): %s', account, exc)
        return {"account": account, "label": account, "vendor_id": "",
                "connected": False, "note": "상태 조회 실패"}


def account_tiles() -> list:
    """4계정 상태 타일. 미설정은 숫자 대신 '미연결'로 나간다."""
    out = []
    for market, market_ko, accounts in ACCOUNT_AXES:
        for a in accounts:
            row = _coupang_account(a) if market == "coupang" else _smartstore_account(a)
            row["market"], row["market_ko"] = market, market_ko
            out.append(row)
    return out


def registration_counts(marketplace: str = "coupang") -> dict:
    """등록 대장 상태별 건수(**누적**). P4 크론이 읽는 그 대장과 같은 소스.

    ※ '오늘' 축은 대장에 집계 함수가 없다 — 여기서 만들지 않는다(발명 0).
       누적임을 화면에 명시한다(라벨이 곧 정직 표기).
    """
    try:
        from src.db import market_registrations_pg as ledger
        if not ledger.enabled():
            return {"connected": False, "note": "등록 대장 미연결(DATABASE_URL 미설정)", "counts": {}}
        return {"connected": True, "note": "", "counts": ledger.counts(marketplace=marketplace)}
    except Exception as exc:
        logger.warning('등록 대장 집계 실패: %s', exc)
        return {"connected": False, "note": "대장 조회 실패", "counts": {}}


def recent_rejections(limit: int = 5, marketplace: str = "coupang") -> dict:
    """P4 반려 감시 큐 최근 N건. 감시 크론이 쓰는 `watch_queue`가 그대로 소스다."""
    try:
        from src.db import market_registrations_pg as ledger
        if not ledger.enabled():
            return {"connected": False, "note": "등록 대장 미연결", "rows": []}
        rows = ledger.watch_queue(marketplace=marketplace, limit=int(limit or 5)) or []
        return {"connected": True, "note": "", "rows": rows[:int(limit or 5)]}
    except Exception as exc:
        logger.warning('반려 큐 조회 실패: %s', exc)
        return {"connected": False, "note": "큐 조회 실패", "rows": []}


def sourcing_queue(seller_ids=None) -> dict:
    """소싱 대기 큐 — 수집 이력 요약(기존 `summary`). 오늘/전체는 그 함수가 이미 준다."""
    try:
        from src.seller_console import collect_history_store as store
        s = store.summary(seller_ids=seller_ids) if seller_ids else store.summary()
        return {"connected": True, "note": "",
                "today": int(s.get("today") or 0), "total": int(s.get("total") or 0)}
    except Exception as exc:
        logger.warning('수집 요약 조회 실패: %s', exc)
        return {"connected": False, "note": "수집 이력 조회 실패", "today": 0, "total": 0}


def build(seller_ids=None, *, reject_limit: int = 5) -> dict:
    """대시보드 한 판. 각 블록은 독립적으로 실패할 수 있고, 실패는 '미연결'로 정직 표기된다."""
    return {
        "accounts": account_tiles(),
        "registrations": registration_counts(),
        "rejections": recent_rejections(limit=reject_limit),
        "sourcing": sourcing_queue(seller_ids),
    }

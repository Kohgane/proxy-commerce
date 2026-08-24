"""src/seller_console/translate_worker.py — v88-B: 백그라운드 번역 워커(드레인).

설계 = docs/design/background-translation.md §5·6. 요청 경로에서 분리된 실제 체인 호출을 여기서 수행.
재사용(발명 최소): AITranslator.translate_product(체인·W10 캡 그대로) · collect_history_store(저장) ·
  #617 원문 소스 규칙 · W7a classify(원인 4분) · translation_usage(쿼터, 성공분만 차감 — 회계 불변).
"""
from __future__ import annotations

import json
import logging
import os
import time

logger = logging.getLogger(__name__)

# 원인 4분(W7a) → 재시도 여부. auth/quota=재시도 무의미(터미널). rate_limit/budget/transient=재시도.
_TERMINAL_CAUSES = {"auth", "quota"}

# 시간예산 드레인 — 외부 크론(cron-job.org 30s 타임아웃) 안에 반드시 응답한다([[동기 대량 라우트 타임아웃 지뢰]]).
# 25초 도달 시 즉시 중단·부분 결과 반환(HTTP 200), 남은 건은 다음 크론 호출이 이어서 처리. env로 조정.
#   ※ 항목당 최악 지연은 W10 요청예산 캡(TRANSLATE_REQUEST_BUDGET_SEC, 기본 8s). 25s + 진행중 1건(≤8s) ≈ 33s
#     여유가 빠듯하면 TRANSLATE_DRAIN_BUDGET_SEC를 20 안팎으로 낮춘다(30s 계약 우선).
_DRAIN_BUDGET_DEFAULT_SEC = 25.0


def _drain_budget_sec() -> float:
    try:
        v = float(os.getenv("TRANSLATE_DRAIN_BUDGET_SEC", "") or _DRAIN_BUDGET_DEFAULT_SEC)
        return v if v > 0 else _DRAIN_BUDGET_DEFAULT_SEC
    except (TypeError, ValueError):
        return _DRAIN_BUDGET_DEFAULT_SEC


def _pending_remaining() -> int:
    """남은 대기(pending) 작업 수 — 조용한 누락 방지·진행상태 노출. 조회 실패 시 -1(미상 정직)."""
    try:
        from src.db import translation_jobs_pg as jobs
        return int(jobs.counts().get("pending", 0))
    except Exception:
        return -1


def _retryable(cause: str) -> bool:
    return (cause or "").lower() not in _TERMINAL_CAUSES


def _worker_id() -> str:
    return f"w-{os.getpid()}"


def drain_once(limit: int = 10, *, worker_id: str = "", time_budget_sec: float = None,
               monotonic_fn=None) -> dict:
    """대기 작업을 **시간예산 안에서** 처리(SKIP LOCKED). PG 미가동이면 정직 no-op.

    시간예산 드레인([[동기 대량 라우트 타임아웃 지뢰]] 재발 방지): 핸들러 시작 시각을 기록하고 **항목 하나
    처리할 때마다 경과를 확인** — time_budget_sec(기본 25s) 도달 시 **즉시 중단**하고 부분 결과를 반환한다.
    항상 외부 크론 타임아웃(30s) 안에 응답하는 것이 계약. 남은 건은 **다음 크론 호출이 이어서 처리**(무상태 재개).
    한 항목씩 lease(1) → 처리 → 커밋이라 중단 시 미처리 리스가 남지 않는다(스트랜딩 0).
    반환에 ``remaining``·``budget_exhausted``·``elapsed_sec`` 포함(진행상태 정직 노출).
    """
    from src.db import translation_jobs_pg as jobs
    if not jobs.enabled():
        return {"ok": False, "reason": "pg 미가동 — 백그라운드 번역 비활성(동기 경로 사용)", "processed": 0,
                "remaining": 0, "budget_exhausted": False}

    from . import collect_history_store, translation_usage
    try:
        from .ai.translator import AITranslator, classify_translate_error
        translator = AITranslator()
    except Exception as exc:            # 번역기 로드 실패 → 처리 안 함(작업은 pending 유지)
        logger.warning("번역기 로드 실패(워커): %s", exc)
        return {"ok": False, "reason": "translator 로드 실패", "processed": 0,
                "remaining": _pending_remaining(), "budget_exhausted": False}

    budget = float(time_budget_sec) if time_budget_sec is not None else _drain_budget_sec()
    clock = monotonic_fn or time.monotonic
    start = clock()
    wid = worker_id or _worker_id()
    summ = {"ok": True, "processed": 0, "success": 0, "failed": 0, "retried": 0, "skipped": 0}
    _unlimited_env = os.getenv("TRANSLATION_UNLIMITED", "0") == "1"
    _limit = translation_usage.free_limit()

    budget_exhausted = False
    while summ["processed"] < int(limit):
        # 항목 착수 전 예산 확인 — 25초 도달이면 즉시 중단(진행중 항목 스트랜딩 0: 아직 lease 안 함).
        if clock() - start >= budget:
            budget_exhausted = True
            break
        leased = jobs.lease(1, worker_id=wid)
        if not leased:                  # 큐 소진 — 정상 종료.
            break
        job = leased[0]
        summ["processed"] += 1
        jid, uid, item_id = job["job_id"], job["user_id"], job["item_id"]
        item = collect_history_store.get(item_id, seller_ids={uid} if uid else None)
        if not item:
            jobs.fail(jid, cause="not_found", error="항목 없음", retryable=False)
            summ["failed"] += 1
            continue
        try:
            extra = json.loads(item.get("extra_json") or "{}")
        except (TypeError, ValueError):
            extra = {}
        # #617: 원문 소스(표시 번역본 아님). 제목=title_en/title, 상세=원본 description만.
        title = (extra.get("title_en") or extra.get("title") or item.get("title") or "").strip()
        desc = (extra.get("description") or "").strip()
        if not (title or desc):
            jobs.fail(jid, cause="empty", error="번역할 원문 없음", retryable=False)
            summ["failed"] += 1
            continue
        # 무료 쿼터(회계 불변) — 무제한 아니고 소진이면 quota 터미널.
        unlimited = _unlimited_env
        try:
            from . import billing_store
            if billing_store.is_unlimited(uid):
                unlimited = True
        except Exception:
            pass
        if not unlimited and translation_usage.get_used(uid) >= _limit:
            jobs.fail(jid, cause="quota", error="무료 번역 한도 소진", retryable=False)
            summ["failed"] += 1
            continue
        # 실제 체인 호출(W10 요청 예산 캡은 translate_product 내부에서 그대로 적용 — 이중 안전망).
        try:
            out = translator.translate_product({"title": title, "description": desc})
        except Exception as exc:
            cause = classify_translate_error(exc)
            state = jobs.fail(jid, cause=cause, error=str(exc), retryable=_retryable(cause))
            summ["retried" if state == "pending" else "failed"] += 1
            continue
        provider = out.get("provider", "stub")
        real = provider not in ("none", "stub", "")
        if not real:
            # 키 미설정/stub → 번역 미실행. 원인이 있으면 그 원인, 없으면 auth(키 미설정)로 터미널.
            cause = classify_translate_error(out.get("error")) if out.get("error") else "auth"
            state = jobs.fail(jid, cause=cause, error=str(out.get("error") or "stub"),
                              retryable=_retryable(cause))
            summ["retried" if state == "pending" else "failed"] += 1
            continue
        title_ko = (out.get("title_ko") or "").strip() or title
        desc_ko = (out.get("description_ko") or "").strip() or desc
        title_ok = bool(title_ko and title_ko != title)
        desc_ok = bool(desc and desc_ko and desc_ko != desc)
        extra["title_ko"] = title_ko
        if desc:                               # #617: 원본 있을 때만 갱신(빈값 클로버 금지)
            extra["description_ko"] = desc_ko
        extra["translated"] = True
        extra["translation_provider"] = provider
        extra["title_translated"] = title_ok
        extra["desc_translated"] = desc_ok
        extra["translate_requested"] = True
        if out.get("detected_lang"):
            extra["translation_lang"] = out.get("detected_lang")
        extra.pop("translate_error", None)
        fields = {"extra_json": json.dumps(extra, ensure_ascii=False)}
        if title_ko and title_ko != item.get("title"):
            fields["title"] = title_ko
        collect_history_store.update(item_id, seller_ids={uid} if uid else None, **fields)
        # 쿼터: 성공분만 차감(회계 불변).
        if not unlimited:
            try:
                translation_usage.increment(uid, 1)
            except Exception as exc:
                logger.warning("번역 사용량 증가 실패(워커): %s", exc)
        jobs.complete(jid, provider=provider, result={
            "title_ko": title_ko, "description_ko": (desc_ko if desc else None),
            "title_ok": title_ok, "desc_ok": desc_ok, "provider": provider,
            "attempts": out.get("attempts"), "detected_lang": out.get("detected_lang")})
        summ["success"] += 1

    summ["budget_exhausted"] = budget_exhausted
    summ["remaining"] = _pending_remaining()
    summ["elapsed_sec"] = round(clock() - start, 2)
    return summ

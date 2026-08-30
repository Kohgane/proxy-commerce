"""src/pricing/cron.py — 자동 재가격 cron 라우트 (Phase 136).

라우트:
    POST /cron/reprice   — Render Cron Job 또는 외부 스케줄러 훅
"""
from __future__ import annotations

import logging
import os
import threading as _threading

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

cron_bp = Blueprint("pricing_cron", __name__, url_prefix="/cron")


@cron_bp.post("/reprice")
def reprice():
    """자동 재가격 실행.

    헤더 ``X-Cron-Secret`` 이 ``CRON_SECRET`` 환경변수와 일치해야 실행.
    (Render 크론 잡에서 헤더 없이 호출 가능하도록 키 미설정 시 허용)

    Query Params:
        dry_run=1|0  — 환경변수 PRICING_DRY_RUN 오버라이드
    """
    # 간단한 시크릿 검증
    cron_secret = os.getenv("CRON_SECRET")
    if cron_secret:
        provided = request.headers.get("X-Cron-Secret", "")
        if provided != cron_secret:
            return jsonify({"ok": False, "error": "Unauthorized"}), 401

    # dry_run 파라미터
    dry_run_param = request.args.get("dry_run")
    if dry_run_param is not None:
        dry_run = dry_run_param == "1"
    else:
        dry_run = None  # 엔진에서 PRICING_DRY_RUN 환경변수 사용

    try:
        from src.pricing.engine import PricingEngine
        engine = PricingEngine()
        results = engine.evaluate(dry_run=dry_run)
    except Exception as exc:
        logger.error("재가격 엔진 오류: %s", exc)
        return jsonify({"ok": False, "error": "재가격 실행 중 오류가 발생했습니다."}), 500

    # 요약 알림 발송
    _send_summary_notification(results)

    return jsonify({"ok": True, "results": results})


@cron_bp.post("/sourcing-monitor")
def sourcing_monitor_cron():
    """수집 상품 소싱처 변화 자동 확인 (Render Cron / 외부 스케줄러 훅).

    헤더 ``X-Cron-Secret`` 이 ``CRON_SECRET`` 환경변수와 일치해야 실행.
    (키 미설정 시 허용 — Render 크론에서 헤더 없이 호출 가능)

    Query Params:
        days, max_items, stale_hours — 확인 범위/주기 조정(선택).
    """
    cron_secret = os.getenv("CRON_SECRET")
    if cron_secret:
        if request.headers.get("X-Cron-Secret", "") != cron_secret:
            return jsonify({"ok": False, "error": "Unauthorized"}), 401

    def _int(name, default):
        try:
            return int(request.args.get(name, default))
        except (TypeError, ValueError):
            return default

    try:
        from src.seller_console.views import run_auto_source_monitor
        summary = run_auto_source_monitor(
            days=_int("days", 14),
            max_items=_int("max_items", 200),
            only_stale_hours=float(request.args.get("stale_hours", 6) or 6),
        )
    except Exception as exc:
        logger.error("소싱처 자동확인 오류: %s", exc)
        return jsonify({"ok": False, "error": "소싱처 자동확인 중 오류가 발생했습니다."}), 500

    return jsonify({"ok": True, **summary})


@cron_bp.post("/supabase-backup")
def supabase_backup_cron():
    """PG(1차 저장소) → Google Sheets **읽기전용 백업** 일 1회 스냅샷 덤프.

    헤더 ``X-Cron-Secret`` 이 ``CRON_SECRET`` 환경변수와 일치해야 실행(미설정 시 허용).
    PG 미설정/시트 미설정이면 정직 사유 반환(가짜 성공 0).
    """
    cron_secret = os.getenv("CRON_SECRET")
    if cron_secret:
        if request.headers.get("X-Cron-Secret", "") != cron_secret:
            return jsonify({"ok": False, "error": "Unauthorized"}), 401
    try:
        from src.db.backup import backup_to_sheets
        summary = backup_to_sheets()
    except Exception as exc:
        logger.error("Supabase 백업 오류: %s", exc)
        return jsonify({"ok": False, "error": "백업 실행 중 오류가 발생했습니다."}), 500
    return jsonify(summary)


# 크론 틱 공유 벽시계 예산 — 외부 크론(cron-job.org 30s)이 두 작업(번역 드레인 + 파일럿 마감) 스택을
# 타임아웃 시키지 않도록 한 요청 전체를 벽시계로 캡([[동기 대량 라우트 타임아웃 지뢰]] 재발 대응).
#   ※ 항목당 최악 지연(번역 W10 8s · 파일럿 수집+사이드로드 수초)이 있어, 예산 도달 후 진행중 1건이 초과할 수
#     있다. cron이 여전히 빨강이면 CRON_TICK_BUDGET_SEC를 낮춘다(30s 계약 우선). 남은 건은 다음 틱 재개.
# cron-job.org의 30초 타임아웃은 **플랫폼 하드 상한**(못 늘림). 틱은 즉시 202 반환 + 실작업(번역 드레인 +
# 파일럿 부활/마감)은 **백그라운드 스레드**로 — 30초 내 응답 보장이 유일한 계약([[동기 대량 라우트 타임아웃 지뢰]]).
#   진입 가드: 이전 틱 미완이면 스킵(중복 스레드 금지). 스레드는 벽시계 예산으로 자기종료(락 무한 점유 방지).
#   ★ 다중 워커 안전의 근본은 멱등성(번역 SKIP LOCKED 리스 · 파일럿 WC 상태) — 락은 워커 내 중복 방지용.
_CRON_TICK_BUDGET_DEFAULT = 45.0   # 스레드 자기종료 상한(응답 아님). 크론 간격(60s)·워커 타임아웃(120s) 아래.
_DRAIN_SHARE_DEFAULT = 20.0        # 번역 드레인 몫(상한). 파일럿 부활/마감이 굶지 않게 나머지 예약.
_PILOT_MIN_SEC = 5.0              # 파일럿에 예약하는 최소 예산(부활 패스가 매 틱 돌게).

_tick_lock = _threading.Lock()     # 워커 내 중복 틱 진입 가드
_last_tick: dict = {}              # 최근 틱 소요/결과(로그·진단) — 어느 작업이 오래 걸렸는지 실측


def _tick_budget_sec() -> float:
    try:
        v = float(os.getenv("CRON_TICK_BUDGET_SEC", "") or _CRON_TICK_BUDGET_DEFAULT)
        return v if v > 0 else _CRON_TICK_BUDGET_DEFAULT
    except (TypeError, ValueError):
        return _CRON_TICK_BUDGET_DEFAULT


def _drain_share_sec() -> float:
    try:
        v = float(os.getenv("TRANSLATE_DRAIN_BUDGET_SEC", "") or _DRAIN_SHARE_DEFAULT)
        return v if v > 0 else _DRAIN_SHARE_DEFAULT
    except (TypeError, ValueError):
        return _DRAIN_SHARE_DEFAULT


def _run_full_tick(app, limit: int, pilot_chunk: int, tick_budget: float) -> dict:
    """실작업(번역 드레인 + 파일럿 부활·마감)을 벽시계 예산 안에서 수행. **락은 호출부가 잡고, 여기서 반드시 해제.**

    per-작업 소요시간을 로그로 남긴다(어느 작업이 30s를 넘겼는지 실측). 예외는 삼키되 사유 기록(조용한 정지 금지).
    """
    import time as _t
    t0 = _t.monotonic()
    result: dict = {"limit": limit}
    try:
        with app.app_context():
            drain_budget = max(4.0, min(_drain_share_sec(), tick_budget - _PILOT_MIN_SEC))
            try:
                from src.seller_console.translate_worker import drain_once
                d = drain_once(limit=limit, time_budget_sec=drain_budget)
            except Exception as exc:               # noqa: BLE001 — 조용한 실패 금지
                logger.error("번역 드레인 오류(백그라운드): %s", exc)
                d = {"ok": False, "error": str(exc), "processed": 0}
            drain_sec = _t.monotonic() - t0
            pilot_budget = tick_budget - (_t.monotonic() - t0)
            if pilot_budget >= _PILOT_MIN_SEC:
                try:
                    pf = _run_pilot_finish_tick(chunk=pilot_chunk, time_budget_sec=pilot_budget)
                except Exception as exc:           # noqa: BLE001
                    logger.warning("파일럿 마감 피기백 스킵(백그라운드): %s", exc)
                    pf = {"skipped": str(exc)}
            else:
                pf = {"skipped": f"번역이 예산 사용({drain_sec:.1f}s) — 다음 틱에서 파일럿"}
            total = _t.monotonic() - t0
            pilot_sec = total - drain_sec
            # 실측 로깅 — 어느 작업이 오래 걸렸는지(30s 초과 표시). cron 판정은 즉답이라, 실작업 결과는 여기로.
            #   파일럿: 게이트 skip(완료 캐시) vs 부활상태(no_targets 정상 / list_failed 이상) 구분 로그.
            if pf.get("gated"):
                logger.info("틱 완료: 번역 %.1fs(처리 %s·잔여 %s) · 파일럿 skip(완료 캐시·WC 조회 0) · 총 %.1fs",
                            drain_sec, d.get("processed"), d.get("remaining"), total)
            elif pf.get("list_failed"):
                logger.warning("틱 완료: 번역 %.1fs · 파일럿 WC 조회 실패(이상, 부활 판정 불가) · 총 %.1fs",
                               drain_sec, total)
            else:
                logger.info(
                    "틱 완료: 번역 %.1fs(처리 %s·잔여 %s) · 파일럿 %.1fs(부활 %s[%s]·백필 %s·잔여 %s·예산소진 %s) · 총 %.1fs%s",
                    drain_sec, d.get("processed"), d.get("remaining"),
                    pilot_sec, pf.get("revived"), pf.get("revive_status"), pf.get("backfilled"),
                    pf.get("remaining_pending"), pf.get("budget_exhausted"), total,
                    "  ⚠️30s초과" if total > 30 else "")
            result.update({"drain": d, "pilot": pf, "drain_sec": round(drain_sec, 1),
                           "pilot_sec": round(pilot_sec, 1), "total_sec": round(total, 1)})
    except Exception as exc:                       # noqa: BLE001 — 최상위 방어(락 해제 보장)
        logger.error("틱 실행 오류(백그라운드): %s", exc)
        result["error"] = str(exc)
    finally:
        _last_tick.clear()
        _last_tick.update(result)
        try:
            _tick_lock.release()
        except RuntimeError:                       # 이미 해제됨(방어)
            pass
    return result


def _spawn_background_tick(app, limit: int, pilot_chunk: int, tick_budget: float):
    """실작업 스레드 시작(daemon). 테스트는 이 함수를 몽키패치해 동기/기록으로 대체."""
    th = _threading.Thread(target=_run_full_tick, args=(app, limit, pilot_chunk, tick_budget),
                           name="translate-pilot-tick", daemon=True)
    th.start()
    return th


@cron_bp.post("/translate-drain")
def translate_drain_cron():
    """v88-B 번역 드레인 + v88-C 파일럿 마감 — **즉시 202 + 백그라운드 스레드**(cron-job.org 30s 하드 상한).

    [[동기 대량 라우트 타임아웃 지뢰]]: 번역 드레인 + 파일럿 부활/마감 두 무거운 외부 I/O를 한 요청에 스택하면
    30s를 넘긴다. cron-job.org 30s는 플랫폼 상한(못 늘림) → **틱은 즉시 202(작업 시작됨)만 반환**하고 실작업은
    백그라운드 스레드에서 벽시계 예산 안에 수행. cron 판정 = **202 즉답 = 성공**, 실작업 결과는 Render 로그.
    **중복 진입 가드**: 이전 틱 미완이면 스킵(중복 스레드 금지). 헤더 ``X-Cron-Secret`` 검증. Query: limit·pilot_chunk.
    """
    from flask import current_app
    cron_secret = os.getenv("CRON_SECRET")
    if cron_secret:
        if request.headers.get("X-Cron-Secret", "") != cron_secret:
            return jsonify({"ok": False, "error": "Unauthorized"}), 401
    try:
        limit = int(request.args.get("limit", 10))
    except (TypeError, ValueError):
        limit = 10
    try:
        pilot_chunk = int(request.args.get("pilot_chunk", 3))
    except (TypeError, ValueError):
        pilot_chunk = 3

    # 동기 검증 모드(?sync=1) — 수동 확인 전용(cron-job.org 아님). 번역 드레인을 **인라인 실행**해
    #   processed·remaining·budget_exhausted를 응답으로 반환(3회 연속 호출로 remaining 감소 수렴 확인).
    #   ※ 30s를 넘을 수 있으니 cron-job.org엔 쓰지 말 것(그쪽은 sync 없이 202 async 유지).
    if str(request.args.get("sync", "")).lower() in ("1", "true", "yes"):
        import time as _t
        if not _tick_lock.acquire(blocking=False):
            return jsonify({"ok": True, "status": "already_running", "skipped": True,
                            "message": "백그라운드 틱 진행 중 — sync 스킵",
                            "last_tick": {k: _last_tick.get(k) for k in ("total_sec", "drain_sec", "pilot_sec")}}), 200
        try:
            t0 = _t.monotonic()
            from src.seller_console.translate_worker import drain_once
            d = drain_once(limit=limit, time_budget_sec=_tick_budget_sec())
        except Exception as exc:
            logger.error("sync 번역 드레인 오류: %s", exc)
            return jsonify({"ok": False, "error": "번역 드레인 중 오류가 발생했습니다."}), 500
        finally:
            try:
                _tick_lock.release()
            except RuntimeError:
                pass
        d["mode"] = "sync"
        d["route_elapsed_sec"] = round(_t.monotonic() - t0, 2)
        return jsonify(d), 200

    # 중복 틱 진입 가드 — 이전 작업 미완이면 새 스레드 안 띄우고 스킵(202).
    if not _tick_lock.acquire(blocking=False):
        return jsonify({"ok": True, "status": "already_running", "skipped": True,
                        "message": "이전 틱이 아직 진행 중 — 이번 호출은 스킵합니다.",
                        "last_tick": {k: _last_tick.get(k) for k in ("total_sec", "drain_sec", "pilot_sec")}}), 202

    app = current_app._get_current_object()
    tick_budget = _tick_budget_sec()
    try:
        _spawn_background_tick(app, limit, pilot_chunk, tick_budget)
    except Exception as exc:                       # 스레드 시작 실패 → 락 해제 후 정직 실패
        try:
            _tick_lock.release()
        except RuntimeError:
            pass
        logger.error("틱 스레드 시작 실패: %s", exc)
        return jsonify({"ok": False, "error": "틱 시작 실패"}), 500
    return jsonify({"ok": True, "status": "accepted",
                    "message": "틱을 백그라운드에서 시작했습니다(작업 결과는 Render 로그에서 확인).",
                    "budget_sec": tick_budget, "limit": limit, "pilot_chunk": pilot_chunk}), 202


_reject_lock = _threading.Lock()   # 반려감시 중복 진입 가드(쿠팡 API 왕복 중복 금지)
_last_reject_watch: dict = {}      # 최근 감시 결과(진단·로그)


def _run_reject_watch(app, account: str, limit: int, budget: float) -> dict:
    """반려감시 실작업(백그라운드) — 등록 대장 → `/histories` 조회·분류·기록·알림. **실행 0**(처방은 승인 게이트 뒤)."""
    import time as _t
    t0 = _t.monotonic()
    out: dict = {"account": account}
    try:
        with app.app_context():
            from src.db import market_registrations_pg as REG
            from src.pipeline import reject_watch as RW
            from src.pipeline.coupang_replicate import _account_creds
            from src.uploaders.coupang_uploader import CoupangUploader
            ak, sk, vid = _account_creds(account)
            if not (ak and sk):
                out = {"ok": False, "error": f"{account} 쿠팡 자격 미설정 — 감시 불가(가짜 결과 0)"}
            else:
                up = CoupangUploader(access_key=ak, secret_key=sk, vendor_id=vid, account=account)
                out = RW.watch_registered(
                    queue_fn=lambda n: REG.watch_queue(account=account, limit=n),
                    history_fn=lambda sid, acct: up.get_status_histories(sid),
                    record_fn=lambda sid, **kw: REG.mark_checked(sid, **kw),
                    notify_fn=_reject_notify_fn(account),
                    limit=limit, time_budget_sec=budget)
            total = _t.monotonic() - t0
            out["total_sec"] = round(total, 1)
            if not out.get("ok"):
                logger.warning("반려감시 실패(%s): %s", account, out.get("error"))
            elif out.get("scanned"):
                logger.info("반려감시 완료(%s): %s · 기록 %s · 알림 %s · %.1fs%s",
                            account, out.get("alert"), out.get("recorded"), out.get("notified"),
                            total, "  ⚠️예산소진" if out.get("budget_exhausted") else "")
            else:
                logger.info("반려감시(%s): 감시 대상 없음(정상 종료) · %.1fs", account, total)
    except Exception as exc:                       # noqa: BLE001 — 조용한 정지 금지
        logger.error("반려감시 오류(백그라운드): %s", exc)
        out = {"ok": False, "error": str(exc)}
    finally:
        _last_reject_watch.clear()
        _last_reject_watch.update(out)
        try:
            _reject_lock.release()
        except RuntimeError:
            pass
    return out


def _reject_notify_fn(account: str):
    """반려 알림 발송기 — 기존 자산 `send_telegram` 재사용(발명 0).

    **가짜 발송 0:** 채널 미설정/dry-run이면 send_telegram이 False를 준다 → 그대로 실패로 올려
    `notified=False` + 사유가 남는다(보냈다고 주장하지 않는다). 내용은 로그에도 남겨 누락 0.
    """
    def _notify(alert: str, rows):
        def _tag(r):
            # 팔리던 상품이 내려간 건은 한눈에 보이게(신규 반려와 구분 — 매출이 즉시 멈춘다).
            return "⚠판매중→반려 " if r.get("was_selling") else ""
        kinds = " · ".join(f"{_tag(r)}{r.get('kind_ko')}({r.get('sid')})"
                           for r in rows[:5] if r.get("comment"))
        # **미분류는 사유 원문 앞 80자를 동봉** — 오너가 Wing을 안 열고도 1차 판단할 수 있게.
        unknown_lines = []
        for r in rows:
            if r.get("kind") == "unknown" and r.get("comment"):
                head = " ".join(str(r["comment"]).split())[:80]
                unknown_lines.append(f"· {r.get('sid')}: {head}")
            if len(unknown_lines) >= 3:                    # 알림이 길어지지 않게 상위 3건만
                break
        body = f"[고가브릿지] 쿠팡 반려 감지 · {account}\n{alert}" + (f"\n{kinds}" if kinds else "")
        if unknown_lines:
            body += "\n미분류 사유 원문:\n" + "\n".join(unknown_lines)
        from src.notifications.telegram import send_telegram
        logger.info("반려 알림: %s", body.replace("\n", " | "))
        if not send_telegram(body, urgency="warning"):
            raise RuntimeError("알림 채널 미설정 또는 발송 실패(TELEGRAM_BOT_TOKEN/CHAT_ID)")
    return _notify


@cron_bp.post("/reject-watch")
def reject_watch_cron():
    """등록 파이프 P4 반려감시 — **즉시 202 + 백그라운드**(Bluehost rej_watch 2h 크론 이식).

    등록 대장(market_registrations)의 미확정 건을 쿠팡 `/histories`로 조회해 **3유형 분류·처방·기록·알림**까지.
    **처방 실행은 여기서 안 한다**(비가역 — 오너 승인 게이트 `/admin/reject-watch/apply` 뒤).
    [[동기 대량 라우트 타임아웃 지뢰]] 회피: 즉답 202, 실작업은 벽시계 예산 안에서 백그라운드.
    권장 주기 = 2시간(원본 크론과 동일). Query: account(gogane|woojoo)·limit.
    """
    from flask import current_app
    cron_secret = os.getenv("CRON_SECRET")
    if cron_secret and request.headers.get("X-Cron-Secret", "") != cron_secret:
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    account = (request.args.get("account") or "gogane").strip().lower()
    if account not in ("gogane", "woojoo"):
        return jsonify({"ok": False, "error": f"알 수 없는 계정: {account}"}), 400
    try:
        limit = int(request.args.get("limit", 30))
    except (TypeError, ValueError):
        limit = 30
    if not _reject_lock.acquire(blocking=False):
        return jsonify({"ok": True, "status": "already_running", "skipped": True,
                        "message": "이전 감시가 진행 중 — 이번 호출은 스킵합니다.",
                        "last": {k: _last_reject_watch.get(k) for k in ("scanned", "alert", "total_sec")}}), 202
    app = current_app._get_current_object()
    budget = _tick_budget_sec()
    try:
        _spawn_reject_watch(app, account, limit, budget)
    except Exception as exc:
        try:
            _reject_lock.release()
        except RuntimeError:
            pass
        logger.error("반려감시 스레드 시작 실패: %s", exc)
        return jsonify({"ok": False, "error": "감시 시작 실패"}), 500
    return jsonify({"ok": True, "status": "accepted", "account": account, "limit": limit,
                    "budget_sec": budget,
                    "message": "반려감시를 백그라운드에서 시작했습니다(결과는 Render 로그·감시 화면)."}), 202


def _spawn_reject_watch(app, account: str, limit: int, budget: float):
    """감시 스레드 시작(daemon). 테스트는 이 함수를 몽키패치해 동기 실행으로 대체."""
    th = _threading.Thread(target=_run_reject_watch, args=(app, account, limit, budget),
                           name="reject-watch-tick", daemon=True)
    th.start()
    return th


# 파일럿 완료 캐시(프로세스) — 수렴 후 매 틱 무거운 WC 전체 조회 고정비를 없앤다(오너 지시).
#   done=True면 즉시 skip(0.1s·로그 1줄). 워커 재시작 시 리셋 → 1틱 재검증 후 재설정.
_pilot_done = {"done": False}


def reset_pilot_done_cache():
    """완료 캐시 리셋 — 새 작업 유입/강제 재실행 시. /pilot-drain?force=1 로 호출."""
    _pilot_done["done"] = False


def _run_pilot_finish_tick(chunk: int = 5, *, time_budget_sec: float = None) -> dict:
    """v88-C 파일럿 자동 마감 1틱 — 검수표 행 + WC 자격으로 백필→publish 청크 처리.

    **고정비 제거(오너 지시):** ①완료 캐시면 즉시 skip(WC 조회 0). ②WC draft 목록을 틱당 **1회만** 조회해
    부활·백필이 공유(예전 2회 → 1회). 부활이 실제로 갱신했을 때만 백필이 신선 재조회. ③'부활 0'을
    **대상 없음(정상) vs 조회 실패(이상)** 로 구분. 상태 저장소 = WC 자신(멱등·재개).
    """
    from src.pipeline import coupang_replicate as CR
    from src.vendors import woocommerce_client as _wc

    # ① 저비용 게이트 — 완료 상태면 WC 조회 없이 즉시 skip.
    if _pilot_done["done"]:
        return {"skipped": "파일럿 완료(캐시) — WC 조회 생략", "done": True, "gated": True}

    rows = CR.default_pilot_rows()
    if not rows:
        return {"skipped": "검수표 0행(모집단/블랙리스트 미배포)"}
    _list = lambda s="draft": _wc.list_products_by_status(s)
    # ② WC draft 목록 1회 조회(고정비 제거). 조회 실패 = 이상('없음 확인'≠'수집 실패') → 정직 skip.
    try:
        drafts = list(_wc.list_products_by_status("draft") or [])
    except Exception as exc:
        return {"skipped": f"WC draft 조회 실패(이상): {exc}", "list_failed": True}
    # 미실증 종결 방어: permanent_fail 1회 부활(공유 목록 사용).
    revive = CR.pilot_revive_permfail(rows, draft_products=drafts, update_fn=_wc.update_product)
    from src.seller_console.views import _collect_real_draft
    enrich = CR.make_coupang_first_enrich_fn(_collect_real_draft, image_cap=CR.IMAGE_CAP)
    _ref_idx = {"n": 0}
    def _image_ref(u):
        _ref_idx["n"] += 1
        return _wc.sideload_image_to_media(u, index=_ref_idx["n"])
    # 부활이 WC를 갱신했으면 백필은 신선 재조회(스테일 방지). 아니면 공유 목록 재사용(조회 0).
    shared = None if revive.get("revived", 0) > 0 else drafts
    out = CR.pilot_finish_tick(
        rows,
        list_products_fn=_list,
        update_fn=_wc.update_product,
        enrich_fn=enrich,
        chunk=chunk,
        image_cap=CR.IMAGE_CAP,
        stock_patch={"manage_stock": False, "stock_status": "instock"},
        image_ref_fn=_image_ref,
        time_budget_sec=time_budget_sec,       # 청크 항목마다 예산 확인(스택 타임아웃 방지)
        draft_products=shared,
    )
    out["revived"] = revive.get("revived", 0)
    out["revive_status"] = revive.get("status")   # no_targets(정상) / revived / revive_failed
    # ③ 수렴 판정 → 완료 캐시(다음 틱부터 즉시 skip). 부활 대상 없음 + 전행 완료 + 예산 미소진.
    if (out.get("done") and not out.get("budget_exhausted")
            and revive.get("status") == "no_targets" and out.get("remaining_pending") == 0):
        _pilot_done["done"] = True
    return out


@cron_bp.post("/pilot-drain")
def pilot_drain_cron():
    """v88-C: 파일럿 마감 전용 크론 — 백필→publish 청크(회당 기본 5건). 오너 클릭 0.

    헤더 ``X-Cron-Secret`` 이 ``CRON_SECRET`` 과 일치해야 실행(미설정 시 허용).
    진행상태 = WC 실측(멱등·재개). 전행 처리 완료(remaining_pending=0) 시 이미지 있는 draft 자동 publish,
    이미지 0장은 no_image 플래그 + draft 잔류(안 팔릴 상품 공개 방지). Query: chunk(기본 5).
    """
    cron_secret = os.getenv("CRON_SECRET")
    if cron_secret:
        if request.headers.get("X-Cron-Secret", "") != cron_secret:
            return jsonify({"ok": False, "error": "Unauthorized"}), 401
    try:
        chunk = int(request.args.get("chunk", 5))
    except (TypeError, ValueError):
        chunk = 5
    # ?force=1 → 완료 캐시 리셋(새 작업 유입/강제 재실행). 그 외엔 캐시가 고정비를 없앤다.
    if str(request.args.get("force", "")).lower() in ("1", "true", "yes"):
        reset_pilot_done_cache()
    try:
        # 전용 크론도 벽시계 예산 캡(cron-job.org 30s 계약) — 남은 건은 다음 틱 재개.
        result = _run_pilot_finish_tick(chunk=chunk, time_budget_sec=_tick_budget_sec())
    except Exception as exc:
        logger.error("파일럿 마감 드레인 오류: %s", exc)
        return jsonify({"ok": False, "error": f"파일럿 마감 중 오류(자격/네트워크): {exc}"}), 502
    return jsonify({"ok": True, **result})


def _send_summary_notification(results: dict):
    """재가격 결과 요약을 텔레그램 + 이메일로 발송."""
    evaluated = results.get("evaluated", 0)
    changed = results.get("changed", 0)
    details = results.get("details", [])
    errors = results.get("errors", [])
    dry_run = results.get("dry_run", True)

    if changed == 0 and not errors:
        return  # 변경 없으면 알림 스킵

    # 평균 변동율
    avg_delta = 0.0
    if details:
        avg_delta = sum(d.get("delta_pct", 0) for d in details) / len(details)

    # ±10% 이상 큰 변동
    big_changes = [d for d in details if abs(d.get("delta_pct", 0)) >= 10]

    # 적용된 룰 집계
    rule_counter: dict = {}
    for d in details:
        for rule_name in d.get("rules", []):
            rule_counter[rule_name] = rule_counter.get(rule_name, 0) + 1
    rule_summary = ", ".join(f"{k}({v})" for k, v in sorted(rule_counter.items(), key=lambda x: -x[1]))

    mode_label = "🔵 시뮬레이션" if dry_run else "🟢 실제 적용"
    msg = (
        f"🔁 자동 재가격 완료 {mode_label}\n"
        f"- 평가: {evaluated} SKU\n"
        f"- 변경: {changed} SKU ({avg_delta:+.1f}% 평균)\n"
        f"- 큰 변동 (±10% 이상): {len(big_changes)}건\n"
    )
    if rule_summary:
        msg += f"- 적용 룰: {rule_summary}\n"
    if errors:
        msg += f"- 오류: {len(errors)}건\n"
    msg += "- 상세: /seller/pricing/history"

    try:
        from src.notifications.telegram import send_telegram
        send_telegram(msg, urgency="info")
    except Exception as exc:
        logger.warning("재가격 알림 전송 실패: %s", exc)

    # Resend 이메일 요약
    try:
        from src.notifications.email_resend import send_email
        send_email(
            to=os.getenv("ADMIN_EMAIL", ""),
            subject=f"[proxy-commerce] 자동 재가격 완료 — {changed}건 변경",
            html=f"<pre>{msg}</pre>",
        )
    except Exception as exc:
        logger.debug("재가격 이메일 발송 실패 (무시): %s", exc)

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
            logger.info(
                "틱 완료: 번역 %.1fs(처리 %s·잔여 %s) · 파일럿 %.1fs(부활 %s·백필 %s·잔여 %s·예산소진 %s) · 총 %.1fs%s",
                drain_sec, d.get("processed"), d.get("remaining"),
                pilot_sec, pf.get("revived"), pf.get("backfilled"), pf.get("remaining_pending"),
                pf.get("budget_exhausted"), total, "  ⚠️30s초과" if total > 30 else "")
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


def _run_pilot_finish_tick(chunk: int = 5, *, time_budget_sec: float = None) -> dict:
    """v88-C 파일럿 자동 마감 1틱 — 검수표 행 + WC 자격으로 백필→publish 청크 처리.

    상태 저장소 = WC 자신(멱등·재개). 자격/네트워크 실패는 예외로 전파(호출부가 사유 기록).
    """
    from src.pipeline import coupang_replicate as CR
    from src.vendors import woocommerce_client as _wc

    rows = CR.default_pilot_rows()
    if not rows:
        return {"skipped": "검수표 0행(모집단/블랙리스트 미배포)"}
    _list = lambda s="draft": _wc.list_products_by_status(s)
    # 미실증 종결 방어: 구경로 실패로 소급 종결된 permanent_fail 행을 1회 부활(신경로 재검증).
    #   revived 마킹으로 행당 1회 — 부활 후 재실패는 진짜 permanent_fail. 배포 후 첫 틱들에서 자동 소진.
    revive = CR.pilot_revive_permfail(rows, list_products_fn=_list, update_fn=_wc.update_product)
    from src.seller_console.views import _collect_real_draft
    # 이미지 소스 피벗: ①쿠팡 sid 원본(봇차단 회피·릴레이·계정라우팅) → ②소싱처 수집 폴백.
    enrich = CR.make_coupang_first_enrich_fn(_collect_real_draft, image_cap=CR.IMAGE_CAP)
    # URL 사이드로드 400(쿠팡 CDN 확장자·MIME 불명) 회피: 서버가 다운로드→media 업로드→media id 연결.
    _ref_idx = {"n": 0}
    def _image_ref(u):
        _ref_idx["n"] += 1
        return _wc.sideload_image_to_media(u, index=_ref_idx["n"])
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
    )
    out["revived"] = revive.get("revived", 0)
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

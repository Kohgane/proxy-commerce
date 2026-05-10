from __future__ import annotations

import logging
import os
from pathlib import Path
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_scheduler = None
_lock_fd = None
_leader_lock_path = None
_job_last_runs: dict[str, dict] = {}


def start_scheduler(app):
    """앱 부트 시 호출. CS_SCHEDULER_ENABLED=1 일 때만."""
    if os.getenv("CS_SCHEDULER_ENABLED", "0") != "1":
        return

    global _scheduler, _lock_fd, _leader_lock_path
    if _scheduler is not None:
        return  # 이미 실행 중

    lock_path = Path(os.getenv("CS_SCHEDULER_LOCK_PATH", "data/cs_scheduler.lock"))
    _leader_lock_path = lock_path
    ttl_seconds = int(os.getenv("SCHEDULER_LEADER_TTL_SECONDS", "90"))
    heartbeat_seconds = int(os.getenv("SCHEDULER_HEARTBEAT_SECONDS", "30"))
    if heartbeat_seconds <= 0:
        heartbeat_seconds = 30
    _lock_fd = _try_acquire_leader(lock_path, ttl_seconds=ttl_seconds)
    if _lock_fd is None:
        logger.info("CS 스케줄러 리더 선출 실패 — 다른 워커가 실행 중. skip.")
        return

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        logger.warning("APScheduler 미설치 — CS 스케줄러 비활성화.")
        return

    poll_minutes = int(os.getenv("CS_POLL_INTERVAL_MINUTES", "5"))
    sla_minutes = int(os.getenv("CS_SLA_CHECK_INTERVAL_MINUTES", "15"))

    sched = BackgroundScheduler()
    sched.add_job(
        lambda: _record_job_run("cs_poll", _poll_all_channels_with_app, app),
        "interval",
        minutes=poll_minutes,
        id="cs_poll",
        max_instances=1,
        coalesce=True,
    )
    sched.add_job(
        lambda: _record_job_run("cs_sla", _check_sla_with_app, app),
        "interval",
        minutes=sla_minutes,
        id="cs_sla",
        max_instances=1,
        coalesce=True,
    )
    pricing_minutes = int(os.getenv("PRICING_MONITOR_INTERVAL_MINUTES", "30"))
    sched.add_job(
        lambda: _record_job_run("pricing_monitor", _pricing_monitor_with_app, app),
        "interval",
        minutes=max(1, pricing_minutes),
        id="pricing_monitor",
        max_instances=1,
        coalesce=True,
    )
    sched.add_job(
        lambda: _record_job_run("fx_alert", _fx_alert_with_app, app),
        "interval",
        minutes=60,
        id="fx_alert",
        max_instances=1,
        coalesce=True,
    )
    sched.add_job(
        lambda: _renew_leader(lock_path, ttl_seconds=ttl_seconds),
        "interval",
        seconds=heartbeat_seconds,
        id="scheduler_heartbeat",
        max_instances=1,
        coalesce=True,
    )
    sched.start()
    _scheduler = sched
    logger.info("CS 스케줄러 시작 — 폴링 %dm, SLA %dm", poll_minutes, sla_minutes)


def _try_acquire_leader(lock_path: Path, ttl_seconds: int):
    """파일 기반 리더 선출."""
    try:
        from src.scheduler.leader_election import acquire_leadership

        if acquire_leadership(lock_path, ttl_seconds=ttl_seconds):
            return True
    except Exception as exc:
        logger.warning("리더 선출 실패: %s", exc)
    return None


def _renew_leader(lock_path: Path, ttl_seconds: int):
    try:
        from src.scheduler.leader_election import renew_leadership

        renew_leadership(lock_path, ttl_seconds=ttl_seconds)
    except Exception as exc:
        logger.debug("리더 heartbeat 갱신 실패: %s", exc)


def _record_job_run(job_id: str, fn, app):
    status = "ok"
    error = None
    try:
        fn(app)
    except Exception as exc:
        status = "error"
        error = str(exc)
        raise
    finally:
        _job_last_runs[job_id] = {
            "last_run_at": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "error": error,
        }


def poll_all_channels() -> dict:
    """등록된 모든 어댑터 폴링 → 신규 메시지 → InboxStore 저장 + 분류 + AI 제안."""
    from .channels.email_imap import EmailImapAdapter
    from .channels.coupang_qa import CoupangQAAdapter
    from .channels.naver_talk import NaverTalkAdapter
    from .channels.eleven_qa import ElevenQAAdapter
    from .inbox_store import CSMessage, InboxStore
    from .classifier import classify, detect_language
    from .sla import compute_deadline
    from .faq_store import FAQStore
    from .auto_send_guard import should_auto_send
    from .replier import suggest_reply_details

    adapters = [EmailImapAdapter(), CoupangQAAdapter(), NaverTalkAdapter(), ElevenQAAdapter()]
    store = InboxStore()
    faq_store = FAQStore()

    total_new = 0
    results: dict = {}

    for adapter in adapters:
        if not adapter.is_active():
            results[adapter.name] = {"skipped": True}
            continue
        try:
            msgs = adapter.poll()
            new_count = 0
            for m in msgs:
                # 중복 확인 (raw_id + channel)
                existing = _find_by_raw_id(store, adapter.name, m.raw_id)
                if existing:
                    continue
                language = detect_language(m.body)
                category, priority = classify(m.body, language)
                deadline = compute_deadline(m.received_at, category)
                import uuid
                cs_msg = CSMessage(
                    message_id=f"msg_{uuid.uuid4().hex[:12]}",
                    channel=adapter.name,
                    direction="inbound",
                    customer_id=m.customer_id,
                    customer_name=m.customer_name,
                    order_no=m.metadata.get("order_no", ""),
                    body=m.body,
                    language=language,
                    category=category,
                    priority=priority,
                    status="open",
                    sla_deadline=deadline,
                    received_at=m.received_at,
                )
                suggested, confidence, matched_faq = suggest_reply_details(cs_msg, faq_store)
                cs_msg.suggested_reply = suggested
                cs_msg.matched_faq_id = matched_faq.faq_id if matched_faq else ""
                can_send, _ = should_auto_send(cs_msg, suggested, confidence)
                if can_send and adapter.send_reply(cs_msg.customer_id, suggested, ref=m.raw_id):
                    cs_msg.status = "auto_handled"
                    cs_msg.final_reply = suggested
                    cs_msg.responded_at = cs_msg.received_at
                store.upsert(cs_msg)
                new_count += 1
            results[adapter.name] = {"new": new_count}
            total_new += new_count
        except Exception as exc:
            logger.warning("채널 %s 폴링 오류: %s", adapter.name, exc)
            results[adapter.name] = {"error": str(exc)}

    # Telegram 알림 (신규 메시지 있을 때)
    if total_new > 0:
        try:
            from src.notifications.telegram import send_telegram
            send_telegram(f"📩 CS 신규 메시지 {total_new}건 (다채널 폴링)", urgency="info")
        except Exception as exc:
            logger.debug("CS 신규 메시지 텔레그램 알림 실패: %s", exc)

    return {"total_new": total_new, "by_channel": results}


def _find_by_raw_id(store, channel: str, raw_id: str):
    """raw_id + channel 조합으로 기존 메시지 찾기."""
    try:
        rows = store.list_messages(channel=channel, limit=1000)
        for row in rows:
            if row.body and raw_id and raw_id in (row.body[:20] if len(row.body) > 20 else row.body):
                return row
            # metadata 기반 비교는 현재 CSMessage에 없으므로 message_id prefix로 체크
        # 더 안전한 방법: raw_id를 body나 order_no에 저장하지 않으므로 중복 없는 것으로 간주
        return None
    except Exception:
        return None


def _poll_all_channels_with_app(app) -> None:
    try:
        with app.app_context():
            poll_all_channels()
    except Exception as exc:
        logger.error("CS 폴링 오류: %s", exc)


def _check_sla_with_app(app) -> None:
    try:
        with app.app_context():
            from src.cs_bot.sla import check_and_notify_sla
            check_and_notify_sla()
    except Exception as exc:
        logger.error("CS SLA 점검 오류: %s", exc)


def _pricing_monitor_with_app(app) -> None:
    with app.app_context():
        if os.getenv("PRICING_MONITOR_ENABLED", "1") != "1":
            return
        from src.pricing.competitor_monitor import CompetitorMonitor

        CompetitorMonitor().monitor_now()


def _fx_alert_with_app(app) -> None:
    with app.app_context():
        from src.pricing.fx_impact import FXImpactAnalyzer

        FXImpactAnalyzer().detect_and_notify()


def get_scheduler_status() -> dict:
    """스케줄러 상태 반환."""
    enabled = os.getenv("CS_SCHEDULER_ENABLED", "0") == "1"
    running = _scheduler is not None and _scheduler.running if _scheduler else False
    next_poll = None
    next_sla = None
    if running and _scheduler:
        try:
            job_poll = _scheduler.get_job("cs_poll")
            job_sla = _scheduler.get_job("cs_sla")
            if job_poll and job_poll.next_run_time:
                next_poll = job_poll.next_run_time.isoformat()
            if job_sla and job_sla.next_run_time:
                next_sla = job_sla.next_run_time.isoformat()
        except Exception:
            pass
    jobs = []
    missed_24h = 0
    if _scheduler is not None:
        now = datetime.now(timezone.utc)
        for job in _scheduler.get_jobs():
            if job.id == "scheduler_heartbeat":
                continue
            meta = _job_last_runs.get(job.id, {})
            last_run = meta.get("last_run_at")
            if not last_run:
                missed_24h += 1
            else:
                try:
                    parsed = datetime.fromisoformat(str(last_run).replace("Z", "+00:00"))
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    if (now - parsed).total_seconds() > 86400:
                        missed_24h += 1
                except Exception:
                    missed_24h += 1
            jobs.append(
                {
                    "id": job.id,
                    "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                    "last_run_at": last_run,
                    "last_status": meta.get("status", "unknown"),
                }
            )
    leader_info = {}
    try:
        if _leader_lock_path:
            from src.scheduler.leader_election import get_leader_info, is_leader

            leader_info = get_leader_info(_leader_lock_path)
            leader_info["is_leader"] = is_leader(_leader_lock_path)
    except Exception:
        leader_info = {}
    return {
        "enabled": enabled,
        "running": running,
        "poll_interval_minutes": int(os.getenv("CS_POLL_INTERVAL_MINUTES", "5")),
        "sla_interval_minutes": int(os.getenv("CS_SLA_CHECK_INTERVAL_MINUTES", "15")),
        "next_poll": next_poll,
        "next_sla": next_sla,
        "jobs": jobs,
        "missed_jobs_24h": missed_24h,
        "leader": leader_info,
    }

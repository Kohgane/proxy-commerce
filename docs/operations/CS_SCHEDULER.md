# CS 자동 cron 스케줄러 (Phase 138)

## 활성화

```env
CS_SCHEDULER_ENABLED=1
CS_SCHEDULER_LOCK_PATH=data/cs_scheduler.lock
CS_POLL_INTERVAL_MINUTES=5
CS_SLA_CHECK_INTERVAL_MINUTES=15
SCHEDULER_LEADER_TTL_SECONDS=90
SCHEDULER_HEARTBEAT_SECONDS=30
PRICING_MONITOR_ENABLED=1
```

## 동작

- APScheduler (BackgroundScheduler) — Flask 앱 부트 시 `start_scheduler(app)` 호출
- 멀티워커 환경: 파일 기반 leader-election(TTL+heartbeat)으로 단 1개 워커만 cron 실행
- 5분마다: 모든 활성 채널 폴링 → InboxStore 저장 + 분류 + AI 제안
- 15분마다: SLA 점검 → 임박/초과 시 텔레그램 알림
- 30분마다: 경쟁사 가격 모니터링 (`pricing_monitor`)
- 60분마다: 환율 영향 점검 (`fx_alert`)

## 수동 트리거

- `POST /admin/cs/poll-now` — 즉시 폴링 실행
- `POST /admin/cs/check-sla` — 즉시 SLA 점검

## 트러블슈팅

- 스케줄러 미동작: `CS_SCHEDULER_ENABLED=1` 확인
- 잠금 파일 충돌: `data/cs_scheduler.lock` 삭제 후 재시작
- APScheduler 미설치: `pip install APScheduler>=3.10`

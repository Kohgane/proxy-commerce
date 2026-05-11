# 멀티워커 잡 큐 운영 가이드 (Phase 147)

## 개요

Phase 147에서 멀티워커 환경의 중복 실행 방지를 위한 분산 잡 큐 관리자가 추가되었습니다.

## 환경변수

```env
JOB_QUEUE_BACKEND=db          # db | redis (현재: db/파일 fallback)
JOB_QUEUE_MAX_RETRIES=3       # 실패 시 최대 재시도 횟수
JOB_QUEUE_DEAD_LETTER_DAYS=7  # dead letter 보관 일수
JOB_QUEUE_PATH=data/job_queue.jsonl       # 큐 파일 경로
JOB_DEAD_LETTER_PATH=data/job_dead_letter.jsonl  # dead letter 파일 경로
```

## 잡 큐 구조

```
큐 상태:
  queued   → 실행 대기 중
  running  → 워커가 처리 중
  done     → 완료
  failed   → 실패 (재시도 대기)
  dead     → 최대 재시도 초과 → dead letter 이동
```

## 잡 추가 (Enqueue)

```python
from src.jobs.queue_manager import enqueue_job, Job, get_queue

# 헬퍼 함수 사용
job_id = enqueue_job(
    category="sourcing",
    payload={"keyword": "나이키 운동화"},
    idempotency_key="sourcing-nike-2026-05-11",  # 중복 방지
    priority=3,  # 1(높음) ~ 10(낮음)
)

# 직접 Job 객체 생성
q = get_queue()
job = Job(
    category="ads",
    payload={"campaign_id": "C001"},
    idempotency_key="ads-bid-C001-20260511",
    priority=1,
    max_retries=5,
)
q.enqueue(job)
```

## 잡 처리 (Worker)

```python
from src.jobs.queue_manager import get_queue
import socket, os

worker_id = f"{socket.gethostname()}-{os.getpid()}"
q = get_queue()

while True:
    job = q.dequeue(worker_id, category="sourcing")
    if not job:
        time.sleep(5)
        continue
    
    try:
        process_job(job)  # 실제 작업 처리
        q.complete(job.job_id)
    except Exception as e:
        q.fail(job.job_id, str(e))
```

## idempotency_key 중복 방지

```python
# 동일 작업이 이미 대기/실행 중인지 확인
if q.duplicate_check("my-unique-key"):
    print("이미 처리 중, 건너뜀")
else:
    enqueue_job("default", {}, idempotency_key="my-unique-key")
```

## 카테고리별 동시성 제한

```python
from src.jobs.queue_manager import CATEGORY_CONCURRENCY

CATEGORY_CONCURRENCY = {
    "sourcing": 2,   # 소싱은 워커 2개까지
    "ads": 1,        # 광고는 워커 1개만
    "reorder": 1,
    "campaign": 2,
    "returns": 3,
    "omni_sync": 2,
    "default": 4,
}
```

## 우선순위

- 1 (최고) ~ 10 (최저)
- 낮은 숫자가 먼저 처리됨
- 같은 우선순위면 생성 시간순(FIFO)

## Dead Letter 관리

```python
q = get_queue()

# dead letter 목록 조회
for j in q.list_dead_letters():
    print(j.job_id, j.category, j.error)

# 특정 잡 재시도
q.retry_dead("job-id-here")

# 오래된 dead letter 정리 (JOB_QUEUE_DEAD_LETTER_DAYS 기준)
cleaned = q.cleanup_old_dead_letters()
print(f"{cleaned}건 정리됨")
```

## 관리 UI

- `/admin/jobs` — 큐 상태, 워커 분포, 실패 목록, 재시도 버튼
- `/admin/diagnostics` → "⚙️ 큐/락 멀티워커" 섹션

## Redis 백엔드 (Phase 148+ 예정)

현재 `JOB_QUEUE_BACKEND=redis` 설정 시 파일 fallback 사용.
Redis Streams 기반 구현은 Phase 148에서 추가 예정.

## 중복 실행 방지 원리

```
1. enqueue 시 idempotency_key 중복 확인
2. 이미 queued/running 상태면 기존 job_id 반환 (새 잡 미생성)
3. dequeue 시 status=running + locked_by 설정 (다른 워커 dequeue 방지)
4. 완료/실패 처리 후 상태 업데이트
```

## 관련 파일

- `src/jobs/queue_manager.py` — FileJobQueue, Job, enqueue_job
- `src/jobs/__init__.py`
- `src/dashboard/admin_views.py` — /admin/jobs 라우트 + 진단 카드

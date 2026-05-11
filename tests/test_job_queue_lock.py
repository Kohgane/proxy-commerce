"""tests/test_job_queue_lock.py — 멀티워커 잡 큐 락/중복 방지 테스트 (Phase 147)."""
import os
import pytest
import tempfile
import uuid


def make_queue(path=None, dead_path=None):
    from src.jobs.queue_manager import FileJobQueue
    if path is None:
        path = tempfile.mktemp(suffix=".jsonl")
    if dead_path is None:
        dead_path = tempfile.mktemp(suffix=".jsonl")
    return FileJobQueue(path=path, dead_letter_path=dead_path), path, dead_path


def test_enqueue_and_dequeue():
    """잡 추가 후 dequeue 가능해야 한다."""
    from src.jobs.queue_manager import Job
    q, p, dp = make_queue()
    try:
        job = Job(category="sourcing", payload={"url": "https://example.com"})
        jid = q.enqueue(job)
        assert jid == job.job_id

        dequeued = q.dequeue("worker-1")
        assert dequeued is not None
        assert dequeued.job_id == job.job_id
        assert dequeued.status == "running"
        assert dequeued.worker_id == "worker-1"
    finally:
        for f in [p, dp]:
            try: os.unlink(f)
            except: pass


def test_idempotency_key_prevents_duplicate():
    """동일 idempotency_key의 중복 잡 추가를 방지해야 한다."""
    from src.jobs.queue_manager import Job
    q, p, dp = make_queue()
    try:
        key = str(uuid.uuid4())
        job1 = Job(idempotency_key=key, category="ads")
        job2 = Job(idempotency_key=key, category="ads")

        id1 = q.enqueue(job1)
        id2 = q.enqueue(job2)

        # 두 번째는 이미 존재하는 잡 ID를 반환해야 함
        assert id1 == id2
        assert len(q.list_queue()) == 1
    finally:
        for f in [p, dp]:
            try: os.unlink(f)
            except: pass


def test_complete_job():
    """잡 완료 처리가 정상 동작해야 한다."""
    from src.jobs.queue_manager import Job
    q, p, dp = make_queue()
    try:
        job = Job(category="default")
        q.enqueue(job)
        dequeued = q.dequeue("worker-1")
        assert dequeued is not None
        q.complete(dequeued.job_id)
        jobs = q.list_queue()
        # 완료된 잡은 queued/running 리스트에서 제거되지 않지만 status가 done
        done_jobs = [j for j in q._read(q._path) if j.status == "done"]
        assert len(done_jobs) == 1
    finally:
        for f in [p, dp]:
            try: os.unlink(f)
            except: pass


def test_fail_and_retry():
    """실패 시 max_retries 이하면 재시도 상태로 변경되어야 한다."""
    from src.jobs.queue_manager import Job
    q, p, dp = make_queue()
    try:
        job = Job(category="default", max_retries=3)
        q.enqueue(job)
        dequeued = q.dequeue("worker-1")
        assert dequeued is not None
        q.fail(dequeued.job_id, "timeout")

        # 재시도 상태로 복귀
        jobs = q._read(q._path)
        assert len(jobs) == 1
        assert jobs[0].status == "queued"
        assert jobs[0].attempts == 1
    finally:
        for f in [p, dp]:
            try: os.unlink(f)
            except: pass


def test_fail_exceeds_max_retries_moves_to_dead_letter():
    """max_retries 초과 시 dead letter로 이동해야 한다."""
    from src.jobs.queue_manager import Job
    q, p, dp = make_queue()
    try:
        job = Job(category="default", max_retries=2)
        q.enqueue(job)

        # 2번 실패
        for i in range(2):
            dequeued = q.dequeue("worker-1")
            if dequeued:
                q.fail(dequeued.job_id, f"error attempt {i+1}")

        # dead letter에 있어야 함
        dead = q.list_dead_letters()
        assert len(dead) >= 1
        assert dead[-1].status == "dead"

        # 큐에서는 제거됨
        queued = [j for j in q._read(q._path) if j.status == "queued"]
        assert len(queued) == 0
    finally:
        for f in [p, dp]:
            try: os.unlink(f)
            except: pass


def test_retry_dead_letter():
    """dead letter 항목을 재시도로 복구할 수 있어야 한다."""
    from src.jobs.queue_manager import Job
    q, p, dp = make_queue()
    try:
        job = Job(category="default", max_retries=1)
        q.enqueue(job)

        dequeued = q.dequeue("worker-1")
        if dequeued:
            q.fail(dequeued.job_id, "fail once")

        dead = q.list_dead_letters()
        assert len(dead) >= 1
        dead_id = dead[-1].job_id

        ok = q.retry_dead(dead_id)
        assert ok is True

        # 큐로 복귀
        queued = q.list_queue(status="queued")
        assert any(j.job_id == dead_id for j in queued)
    finally:
        for f in [p, dp]:
            try: os.unlink(f)
            except: pass


def test_priority_ordering():
    """우선순위가 낮은 숫자(높은 우선순위) 잡이 먼저 dequeue되어야 한다."""
    from src.jobs.queue_manager import Job
    q, p, dp = make_queue()
    try:
        low_prio = Job(category="default", priority=9)
        high_prio = Job(category="default", priority=1)
        q.enqueue(low_prio)
        q.enqueue(high_prio)

        first = q.dequeue("worker-1")
        assert first is not None
        assert first.priority == 1
    finally:
        for f in [p, dp]:
            try: os.unlink(f)
            except: pass


def test_worker_distribution():
    """worker_distribution()이 워커별 실행 중 작업을 올바르게 반환해야 한다."""
    from src.jobs.queue_manager import Job
    q, p, dp = make_queue()
    try:
        q.enqueue(Job(category="default"))
        q.enqueue(Job(category="sourcing"))
        q.dequeue("worker-A")
        q.dequeue("worker-B")

        dist = q.worker_distribution()
        assert dist.get("worker-A", 0) >= 1
        assert dist.get("worker-B", 0) >= 1
    finally:
        for f in [p, dp]:
            try: os.unlink(f)
            except: pass


def test_summary_keys():
    """summary()가 필요한 키를 모두 포함해야 한다."""
    q, p, dp = make_queue()
    try:
        s = q.summary()
        for key in ("backend", "queued", "running", "dead_letters", "by_category", "worker_distribution", "max_retries"):
            assert key in s, f"summary에서 '{key}' 키 누락"
    finally:
        for f in [p, dp]:
            try: os.unlink(f)
            except: pass


def test_duplicate_check():
    """duplicate_check()가 동일 idempotency_key 대기/실행 중 잡을 감지해야 한다."""
    from src.jobs.queue_manager import Job
    q, p, dp = make_queue()
    try:
        key = "unique-key-001"
        job = Job(idempotency_key=key, category="default")
        q.enqueue(job)

        assert q.duplicate_check(key) is True
        assert q.duplicate_check("other-key") is False
    finally:
        for f in [p, dp]:
            try: os.unlink(f)
            except: pass


def test_enqueue_job_helper():
    """enqueue_job() 헬퍼가 job_id 문자열을 반환해야 한다."""
    from src.jobs.queue_manager import enqueue_job
    import os
    tmp = tempfile.mktemp(suffix=".jsonl")
    tmp_dl = tempfile.mktemp(suffix=".jsonl")
    old_path = os.environ.get("JOB_QUEUE_PATH")
    old_dl = os.environ.get("JOB_DEAD_LETTER_PATH")
    os.environ["JOB_QUEUE_PATH"] = tmp
    os.environ["JOB_DEAD_LETTER_PATH"] = tmp_dl
    try:
        jid = enqueue_job("sourcing", {"keyword": "테스트"}, priority=3)
        assert isinstance(jid, str)
        assert len(jid) > 0
    finally:
        os.environ.pop("JOB_QUEUE_PATH", None)
        os.environ.pop("JOB_DEAD_LETTER_PATH", None)
        if old_path:
            os.environ["JOB_QUEUE_PATH"] = old_path
        if old_dl:
            os.environ["JOB_DEAD_LETTER_PATH"] = old_dl
        for f in [tmp, tmp_dl]:
            try: os.unlink(f)
            except: pass

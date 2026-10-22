import os

bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"
# I/O 바운드(Google Sheets/마켓 API 왕복)라 gthread로 동시성↑ — 워커당 스레드로 블로킹 호출 겹치기 (v8 속도).
# Z10-C(오너 2026-10-13 20:09 KST OOM — Render 512MB): 워커 2개 × (base 160 + 사전검증 잡 146 + 동시 요청) > 512.
#   잡 하나는 상한 아래였고 **합계**가 넘었다 → 워커 1개 · 스레드 8(gthread). 사전검증 1개 + 요청 동시 처리는 스레드로.
#   Render 대시보드에 예전 값 `GUNICORN_WORKERS=2`가 남아 있어도 `GUNICORN_MAX_WORKERS`(기본 1)로 묶는다 —
#   플랜을 올리면(Standard 2GB) 그때 `GUNICORN_MAX_WORKERS`를 올린다.
workers = max(1, min(int(os.getenv('GUNICORN_WORKERS', '1') or 1), int(os.getenv('GUNICORN_MAX_WORKERS', '1') or 1)))
worker_class = os.getenv('GUNICORN_WORKER_CLASS', 'gthread')
threads = int(os.getenv('GUNICORN_THREADS', '8'))
timeout = int(os.getenv('GUNICORN_TIMEOUT', '120'))
# Z7(오너 2026-10-08 OOM): 워커 2개 이상이면 요청 200±50번마다 워커를 갈아끼운다 — 누수 보험(한 워커가 커져도 오래 안 간다).
#   워커 1개면 재시작 순간 받을 곳이 없으므로 켜지 않는다. 0을 주면 끈다.
max_requests = int(os.getenv('GUNICORN_MAX_REQUESTS', '200')) if workers >= 2 else 0
max_requests_jitter = int(os.getenv('GUNICORN_MAX_REQUESTS_JITTER', '50')) if workers >= 2 else 0
graceful_timeout = int(os.getenv('GUNICORN_GRACEFUL_TIMEOUT', '30'))
keepalive = int(os.getenv('GUNICORN_KEEPALIVE', '5'))
accesslog = '-'
# M3-iOS 실측 결함(2026-09-28): 기본 형식의 `%(r)s`(요청 줄)·`%(f)s`(Referer)는 **쿼리를 통째로** 남긴다 —
#   공유 시트 `/seller/collect/share?url=…?tk=…`의 `tk`가 접근 로그에 새고 있었다. 경로(`%(U)s`)만 남긴다.
#   쿼리는 앱 요청 로그(`request_logger._safe_query`)가 스크럽해서 남긴다. start_render.sh와 같은 값.
access_log_format = '%(h)s %(t)s "%(m)s %(U)s %(H)s" %(s)s %(b)s %(M)sms "%(a)s"'
errorlog = '-'
loglevel = os.getenv('GUNICORN_LOG_LEVEL', 'info')
preload_app = True

# Z10-C: 워커 1개에선 이 재시작이 서비스를 잠깐 비운다 — 잡·크론이 없을 때만(아래 `_active_jobs`) · 같은 상한.
# Z10(오너 2026-10-10 22:34·22:35 KST — Render 512MB 초과 2회): 워커 RSS 상한 — 요청이 끝났는데 이 워커가
#   `WORKER_RSS_LIMIT_MB`(기본 380)를 넘었으면 **이 워커만** 조용히 갈아끼운다(받던 요청은 끝내고 나간다).
#   두 워커가 동시에 넘으면 서비스 전체가 비므로, 다른 워커가 최근 `WORKER_RSS_RESTART_GAP_SEC`(60초) 안에 나갔으면 기다린다.
_RSS_LIMIT_MB = int(os.getenv('WORKER_RSS_LIMIT_MB', '380') or 0)
_RSS_GAP_SEC = int(os.getenv('WORKER_RSS_RESTART_GAP_SEC', '60') or 60)
_RSS_STAMP = os.getenv('WORKER_RSS_RESTART_STAMP', '/tmp/kgp_worker_rss_restart')


def _worker_rss_mb():
    try:
        with open('/proc/self/status', encoding='ascii', errors='ignore') as fh:
            for line in fh:
                if line.startswith('VmRSS:'):
                    return int(line.split()[1]) // 1024
    except OSError:
        pass
    return -1


def _active_jobs():
    """지금 이 워커에서 도는 사전검증 잡·크론 이름(샘플러 `watch` 구간). 못 읽으면 빈 목록."""
    try:
        from src.utils import rss_sampler
        return rss_sampler.active_names()
    except Exception:
        return []


# Y15(운영 10-21 17:20~10-22 07:10 — 14시간): 새 잡 문지기는 **인스턴스 합계**(master+워커, `INSTANCE_MEM_START_MAX_MB` 420)로 보고
#   이 재시작은 **워커 RSS**(380)만 봤다. 워커 340MB · 합계 422~435MB에서 문지기는 매 틱 「시작 거부」, 재시작은 「상한 아래」 —
#   일회성 작업 54줄이 밤새 하나도 안 돌았다(서로 풀어 줄 쪽이 없는 교착). 합계가 문지기 상한 이상이면 같은 조건(잡 없음·간격)으로 갈아끼운다.
#   합계 재기는 /proc을 여러 번 읽으므로 `_INST_EVERY_SEC`(60초)에 한 번만.
_INST_EVERY_SEC = int(os.getenv('WORKER_INSTANCE_CHECK_SEC', '60') or 60)
_inst_seen = {'at': 0.0, 'over': False, 'mb': -1, 'lim': 0}


def _instance_over():
    """`(인스턴스 합계 ≥ 새 잡 문지기 상한, 합계 MB, 상한 MB)` — 60초에 한 번 잰다. 못 재면 아니오."""
    import time as _t
    now = _t.time()
    if now - _inst_seen['at'] < _INST_EVERY_SEC:
        return _inst_seen['over'], _inst_seen['mb'], _inst_seen['lim']
    over, mb, lim = False, -1, 0
    try:
        from src.utils import rss as _rss
        lim = _rss.start_limit_mb()
        if lim > 0:
            mb = _rss.instance_mb()
            over = mb >= lim
    except Exception:
        pass
    _inst_seen.update(at=now, over=over, mb=mb, lim=lim)
    return over, mb, lim


def post_request(worker, req, environ, resp):
    if _RSS_LIMIT_MB <= 0 or not getattr(worker, 'alive', False):
        return
    rss = _worker_rss_mb()
    why = ''
    if rss < _RSS_LIMIT_MB:
        over, inst, lim = _instance_over()
        if not over:
            return
        why = f' · 인스턴스 합계 {inst} ≥ 문지기 {lim}'
    # Z10-B(오너 2026-10-11): 잡·크론이 도는 중이면 갈아끼우지 않는다 — 그 잡을 죽이면 카드가 「검증 못 함」으로 끝나고
    #   다시 누르면 같은 일을 처음부터 한다. 잡이 끝난 뒤 첫 요청에서 다시 본다.
    busy = _active_jobs()
    if busy:
        worker.log.warning('[RSS] worker pid=%s rss_mb=%d (상한 %d%s) — 잡 %s 진행 중이라 이번엔 남는다', worker.pid, rss, _RSS_LIMIT_MB, why, busy)
        return
    import time as _t
    try:
        last = os.path.getmtime(_RSS_STAMP)
    except OSError:
        last = 0
    if _t.time() - last < _RSS_GAP_SEC:
        worker.log.warning('[RSS] worker pid=%s rss_mb=%d (상한 %d%s) — 다른 워커가 방금 재시작해 이번엔 남는다', worker.pid, rss, _RSS_LIMIT_MB, why)
        return
    try:
        with open(_RSS_STAMP, 'w') as fh:
            fh.write(str(worker.pid))
    except OSError:
        pass
    worker.log.warning('[RSS] worker pid=%s rss_mb=%d (상한 %d%s) — 이 워커만 재시작(받던 요청은 끝내고)', worker.pid, rss, _RSS_LIMIT_MB, why)
    worker.alive = False

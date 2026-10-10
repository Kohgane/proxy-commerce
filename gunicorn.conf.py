import os

bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"
# I/O 바운드(Google Sheets/마켓 API 왕복)라 gthread로 동시성↑ — 워커당 스레드로 블로킹 호출 겹치기 (v8 속도).
workers = int(os.getenv('GUNICORN_WORKERS', '2'))
worker_class = os.getenv('GUNICORN_WORKER_CLASS', 'gthread')
threads = int(os.getenv('GUNICORN_THREADS', '4'))
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


def post_request(worker, req, environ, resp):
    if _RSS_LIMIT_MB <= 0 or not getattr(worker, 'alive', False):
        return
    rss = _worker_rss_mb()
    if rss < _RSS_LIMIT_MB:
        return
    import time as _t
    try:
        last = os.path.getmtime(_RSS_STAMP)
    except OSError:
        last = 0
    if _t.time() - last < _RSS_GAP_SEC:
        worker.log.warning('[RSS] worker pid=%s rss_mb=%d ≥ %d — 다른 워커가 방금 재시작해 이번엔 남는다', worker.pid, rss, _RSS_LIMIT_MB)
        return
    try:
        with open(_RSS_STAMP, 'w') as fh:
            fh.write(str(worker.pid))
    except OSError:
        pass
    worker.log.warning('[RSS] worker pid=%s rss_mb=%d ≥ %d — 이 워커만 재시작(받던 요청은 끝내고)', worker.pid, rss, _RSS_LIMIT_MB)
    worker.alive = False

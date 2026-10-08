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

import os

bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"
# I/O 바운드(Google Sheets/마켓 API 왕복)라 gthread로 동시성↑ — 워커당 스레드로 블로킹 호출 겹치기 (v8 속도).
workers = int(os.getenv('GUNICORN_WORKERS', '2'))
worker_class = os.getenv('GUNICORN_WORKER_CLASS', 'gthread')
threads = int(os.getenv('GUNICORN_THREADS', '4'))
timeout = int(os.getenv('GUNICORN_TIMEOUT', '120'))
graceful_timeout = int(os.getenv('GUNICORN_GRACEFUL_TIMEOUT', '30'))
keepalive = int(os.getenv('GUNICORN_KEEPALIVE', '5'))
accesslog = '-'
errorlog = '-'
loglevel = os.getenv('GUNICORN_LOG_LEVEL', 'info')
preload_app = True

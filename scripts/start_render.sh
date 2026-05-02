#!/usr/bin/env sh
# scripts/start_render.sh — Render 배포 진입점 스크립트
# 환경변수 가드를 거쳐 gunicorn으로 Flask 앱을 기동합니다.
set -e

PORT="${PORT:-10000}"
APP_ENV="${APP_ENV:-production}"

echo "[start_render] APP_ENV=${APP_ENV}  PORT=${PORT}"

# 마이그레이션 (옵션 — RUN_MIGRATIONS=1 로 활성화)
if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
    echo "[start_render] Running DB migrations..."
    python scripts/migrate.py || { echo "[start_render] Migration failed"; exit 1; }
fi

# 시드 데이터 (옵션 — RUN_SEED=1 로 활성화, 프로덕션에서는 사용 자제)
if [ "${RUN_SEED:-0}" = "1" ] && [ "${APP_ENV}" != "production" ]; then
    echo "[start_render] Running seed data..."
    python scripts/seed.py || { echo "[start_render] Seed failed"; exit 1; }
fi

echo "[start_render] Starting gunicorn on 0.0.0.0:${PORT}..."
exec gunicorn src.order_webhook:app \
    --bind "0.0.0.0:${PORT}" \
    --workers "${GUNICORN_WORKERS:-2}" \
    --timeout "${GUNICORN_TIMEOUT:-120}" \
    --log-level "${GUNICORN_LOG_LEVEL:-info}" \
    --access-logfile - \
    --error-logfile -

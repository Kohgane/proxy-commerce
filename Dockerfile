FROM python:3.11-slim

ARG APP_ENV=production
ARG BUILD_DATE
ARG VCS_REF
ARG VERSION

LABEL org.opencontainers.image.title="proxy-commerce" \
      org.opencontainers.image.description="Proxy commerce order webhook service" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.source="https://github.com/kohgane/proxy-commerce" \
      org.opencontainers.image.licenses="MIT"

WORKDIR /app

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY src/ ./src/
# 크롬 확장 소스 — /seller/extension/download 가 런타임에 ZIP으로 패키징해 내려준다.
COPY extensions/ ./extensions/
COPY gunicorn.conf.py .
COPY config.example.yml .

# Create non-root user and set ownership
RUN adduser --disabled-password --gecos '' appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 10000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:${PORT:-10000}/health || exit 1

ENV PORT=10000 \
    GUNICORN_WORKERS=2 \
    GUNICORN_TIMEOUT=120 \
    APP_ENV=${APP_ENV}

# 운영 스크립트 전체 포함 — 운영자가 Render Shell에서 실행하는 산출물(start_render.sh·
# migrate_to_supabase.py·hygiene_report.py 등)이 배포 이미지에 항상 존재하도록 scripts/ 통째 복사.
# (예전엔 스크립트를 하나씩 COPY해서 신규 산출물이 이미지에서 누락되는 갭이 반복됐다: #423 migrate,
#  v87-W1 hygiene_report. 통째 복사로 재발 봉인. .py 텍스트라 이미지 크기 영향 미미, 런타임 미임포트.)
COPY scripts/ ./scripts/

CMD ["sh", "scripts/start_render.sh"]

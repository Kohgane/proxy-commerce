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

# Copy startup script
COPY scripts/start_render.sh ./scripts/start_render.sh

CMD ["sh", "scripts/start_render.sh"]

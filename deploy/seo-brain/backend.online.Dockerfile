ARG PYTHON_VERSION=3.12-slim
FROM python:${PYTHON_VERSION} AS builder

WORKDIR /build

COPY backend/pyproject.toml backend/pyproject.toml
COPY backend/seo_brain backend/seo_brain

RUN pip install --no-cache-dir setuptools wheel \
    && pip install --no-cache-dir --no-build-isolation --prefix=/install ./backend

FROM python:${PYTHON_VERSION} AS runtime

WORKDIR /app

COPY --from=builder /install /usr/local
COPY backend/cli backend/cli
COPY backend/mcp_server backend/mcp_server
COPY database/migrations database/migrations

ENV PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    SEO_KG_ROOT=/app \
    DATABASE_PATH=/app/runtime-db/seo.db

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3)"]

CMD ["sh", "-c", "mkdir -p /app/runtime-db && if [ ! -s \"$DATABASE_PATH\" ] && [ -s /app/seed/seo.db ]; then cp /app/seed/seo.db \"$DATABASE_PATH\"; fi && python backend/cli/setup.py --vault --db && python backend/cli/api.py --host 0.0.0.0 --port 8000"]

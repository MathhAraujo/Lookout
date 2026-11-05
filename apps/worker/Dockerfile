FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libgdk-pixbuf-2.0-0 \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
COPY apps/api/lookout ./apps/api/lookout

RUN pip install --no-cache-dir -e ".[dev]"

ARG INSTALL_BROWSERS=false
RUN if [ "$INSTALL_BROWSERS" = "true" ]; then \
        python -m playwright install --with-deps chromium; \
    fi \
    && rm -rf /var/lib/apt/lists/*

COPY alembic.ini .
COPY alembic ./alembic
COPY config ./config
COPY templates ./templates

CMD ["python", "-m", "lookout.worker"]
